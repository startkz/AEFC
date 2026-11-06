"""Pre-registered bytes-to-target evaluation on the frozen IEEE39 AC policy.

This module does NOT alter the training update rule. At each federation round
it freezes and hashes all inference actor states, evaluates the same 10 AC
validation demand/attack scenarios, and records the *serialized application*
uplink bytes accrued by the training server. No socket/wire bytes are claimed.

Target threshold is fixed at >=9/10 validation episodes, with both:
  A) >=90% restored load AND 5 successive AC-safe steps
  B) >=90% restored load for 5 successive steps, independent of AC safety
A disjoint, fixed test set is evaluated only after training at selected
frozen validation-target checkpoints and at the terminal checkpoint.
"""
from __future__ import annotations
import copy, hashlib, json, math, os, pathlib, tempfile
import torch

TARGET_LOAD_PCT=90.0
DWELL=5
N_VALIDATION=10
N_TEST=10
MIN_PASSED=9
VALIDATION_SEED_BASE=600000
TEST_SEED_BASE=900000


def _digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as fp:
        for blk in iter(lambda: fp.read(1024*1024), b""):
            h.update(blk)
    return h.hexdigest()


def _episode_from_trace(ep):
    tr=ep["trace"]
    load_dwell=0
    load_hit=False
    joint_dwell=0
    joint_hit=False
    for z in tr:
        qualifies_load=float(z["restored_pct"]) >= TARGET_LOAD_PCT
        qualifies_safe=bool(z["ac_converged"]) and bool(z["safe"]) and (
            float(z["voltage_violation_pu_sum"]) <= 1e-7 and
            float(z["thermal_excess_pct_sum"]) <= 1e-7)
        load_dwell=load_dwell+1 if qualifies_load else 0
        joint_dwell=joint_dwell+1 if qualifies_load and qualifies_safe else 0
        load_hit |= load_dwell>=DWELL
        joint_hit |= joint_dwell>=DWELL
    if bool(ep["safe_dwell5"])!=joint_hit:
        raise ValueError("Episode safe_dwell5 inconsistent with raw 5-step AC trace")
    return {"joint_success":bool(joint_hit),
            "load_only_success":bool(load_hit),
            "terminal_load_pct":float(ep["final_restored_pct"]),
            "safe_dwell5":int(ep["safe_dwell5"]),
            "recovery_step":int(ep["recovery_step"]),
            "trace":tr}


class ByteTargetTracker:
    def __init__(self, root, case, seed, mode, hetero, attack, clients,
                 total_rounds, agent_observation_dims, fixed_traffic):
        self.root=pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots=self.root/"frozen_checkpoints"
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.case=int(case)
        self.seed=int(seed)
        self.mode=str(mode)
        self.hetero=str(hetero)
        self.attack=str(attack)
        self.clients=int(clients)
        self.total_rounds=int(total_rounds)
        self.obs_dims=list(map(int, agent_observation_dims))
        self.fixed_traffic=bool(fixed_traffic)
        self.records=[]
        self.first={"joint":None, "load_only":None}
        self.last_bytes=-1
        self.validation_seeds=[VALIDATION_SEED_BASE+100*self.seed+i for i in range(N_VALIDATION)]
        self.test_seeds=[TEST_SEED_BASE+100*self.seed+i for i in range(N_TEST)]
        if set(self.validation_seeds).intersection(self.test_seeds):
            raise ValueError("validation and independent test seed overlap")
        self.protocol={
            "protocol_id":"IoTJ-76369-BTT-v1-frozen-before-results",
            "case":self.case,"seed":self.seed,"method":self.mode,
            "hetero":self.hetero,"attack":self.attack,
            "clients":self.clients,"planned_rounds":self.total_rounds,
            "load_threshold_pct":TARGET_LOAD_PCT,"safe_dwell_steps":DWELL,
            "validation_n":N_VALIDATION,"test_n":N_TEST,
            "minimum_validation_successes":MIN_PASSED,
            "validation_seeds":self.validation_seeds,
            "test_seeds":self.test_seeds,
            "fixed_traffic":self.fixed_traffic,
            "cumulative_byte_scope":"Actual length of constructed serialized uplink application messages in strict_agent.serialized_size; no TCP/IP headers, retries, or downstream broadcast",
            "analytical_estimates_separate":"Not counted as measured uplink; formulas presented separately, if used",
            "checkpoint_scope":"Inference-only frozen actor state_dicts (not resumable training state)",
            "validation_selection":"First round, including round 0, with >=9/10 episodes passing the precommitted criterion; no test-set tuning",
            "holdout":"Independent test evaluated AFTER all training at validation-selected and terminal checkpoints",
            "physical_scope":"pandapower IEEE39 quasi-static AC; voltage/thermal and five-step safe dwell; not frequency or dynamic protection"
        }
        (self.root/"protocol.json").write_text(json.dumps(self.protocol, indent=2)+"\n",encoding="utf-8")

    def _evaluation(self, actors, seeds, *, with_trace):
        # Import lazily: strict_run imports ByteTargetTracker.
        try:
            from .strict_run import RecoveryGrid, run_episode
        except ImportError:
            from strict_run import RecoveryGrid, run_episode
        # All actors are frozen: explore=False, no replay updates, no gradients.
        episodes=[]
        for ordinal, scenario_seed in enumerate(seeds):
            env=RecoveryGrid(self.case,self.clients,int(scenario_seed),self.hetero,
                             attack=("joint" if self.attack=="joint" else
                                     "physical" if self.attack=="physical" else "clean"))
            result=run_episode(env,actors,False,
                               noise_seed=2000000+int(scenario_seed),trace=True)
            record=_episode_from_trace(result)
            record["scenario_ordinal"]=ordinal
            record["scenario_seed"]=int(scenario_seed)
            if not with_trace:
                record.pop("trace")
            episodes.append(record)
        return {"joint_successes":sum(int(x["joint_success"]) for x in episodes),
                "load_only_successes":sum(int(x["load_only_success"]) for x in episodes),
                "episodes":episodes}

    def snapshot(self, round_1based, agents, cumulative_bytes, uplink_round_bytes):
        r=int(round_1based);total=int(cumulative_bytes);up=int(uplink_round_bytes)
        if r!=len(self.records):raise ValueError("Checkpoint sequence has a missing round")
        if total<0 or up<0 or (self.last_bytes>=0 and total<self.last_bytes):
            raise ValueError("Negative or non-monotone measured byte counter")
        if r==0 and (total or up):
            raise ValueError("Round-zero message bytes must be zero")
        if r>0 and total-self.last_bytes!=up:
            raise ValueError("Round upload bytes disagree with cumulative counter")
        for a in agents:
            a.actor.eval()
        ckpt=self.snapshots/(f"round_{r:04d}.pt")
        snapshot={
            "checkpoint_role":"frozen inference only; not a resumable training state",
            "protocol_id":self.protocol["protocol_id"],
            "round_1based":r,"training_episodes":r*5,
            "cumulative_serialized_uplink_bytes":total,
            "seed":self.seed,"case":self.case,"method":self.mode,
            "hetero":self.hetero,"attack":self.attack,
            "obs_dims":self.obs_dims,
            "actors":[{k:v.detach().cpu().clone() for k,v in a.actor.state_dict().items()}
                      for a in agents],
            "source_commit":os.environ.get("GITHUB_SHA","unavailable")
        }
        torch.save(snapshot,ckpt)
        checksum=_digest(ckpt)
        evaluated=self._evaluation(agents,self.validation_seeds,with_trace=True)
        # Store the original stepwise backend signals so audit does not have to
        # trust the training-set recovery label or inferred terminal averages.
        joint=evaluated["joint_successes"];load=evaluated["load_only_successes"]
        row={
            "round_1based":r,"training_episodes":r*5,
            "uplink_round_bytes":up,
            "cumulative_serialized_uplink_bytes":total,
            "checkpoint_file":str(ckpt.relative_to(self.root)),
            "checkpoint_sha256":checksum,
            "validation_joint_successes":joint,
            "validation_load_only_successes":load,
            "validation_joint_target_met":joint>=MIN_PASSED,
            "validation_load_only_target_met":load>=MIN_PASSED,
            "validation_episodes":evaluated["episodes"]
        }
        self.records.append(row)
        self.last_bytes=total
        for name,hit in (("joint",joint>=MIN_PASSED),("load_only",load>=MIN_PASSED)):
            if hit and self.first[name] is None:
                self.first[name]={"round_1based":r,
                                  "cumulative_serialized_uplink_bytes":total,
                                  "checkpoint_file":row["checkpoint_file"],
                                  "checkpoint_sha256":checksum}
        with (self.root/"round_validation.jsonl").open("a",encoding="utf-8") as fp:
            fp.write(json.dumps(row,allow_nan=False,separators=(",",":"))+"\n")
        with (self.root/"checkpoint_manifest.jsonl").open("a",encoding="utf-8") as fp:
            fp.write(json.dumps({k:row[k] for k in
                ("round_1based","training_episodes","checkpoint_file",
                 "checkpoint_sha256","cumulative_serialized_uplink_bytes")},
                 separators=(",",":"))+"\n")
        for a in agents:a.actor.train()

    def finalize(self,agents,round_summaries):
        if len(self.records)!=self.total_rounds+1:
            raise ValueError("Incomplete frozen checkpoint series")
        if len(round_summaries)!=self.total_rounds:
            raise ValueError("Incomplete training federation rounds")
        if sum(int(z["uplink_bytes"]) for z in round_summaries)!=self.last_bytes:
            raise ValueError("Fed server byte count disagrees with tracker")
        terminal=self.records[-1]
        chosen={"terminal":self.total_rounds}
        for key,value in self.first.items():
            if value is not None:
                chosen["first_validation_"+key]=int(value["round_1based"])
        checkpoint_tests={}
        original=[{k:v.detach().clone() for k,v in a.actor.state_dict().items()}
                  for a in agents]
        try:
            for label,r in chosen.items():
                checkpoint=torch.load(self.snapshots/(f"round_{r:04d}.pt"),
                                      map_location="cpu",weights_only=False)
                for a,actor_sd in zip(agents,checkpoint["actors"]):
                    a.actor.load_state_dict(actor_sd,strict=True)
                    a.actor.eval()
                outcome=self._evaluation(agents,self.test_seeds,with_trace=True)
                checkpoint_tests[label]={
                    "checkpoint_round_1based":r,
                    "checkpoint_sha256":self.records[r]["checkpoint_sha256"],
                    **outcome}
        finally:
            for a,sd in zip(agents,original):
                a.actor.load_state_dict(sd,strict=True);a.actor.train()
        (self.root/"independent_test.json").write_text(
            json.dumps({"selection_used_validation_only":True,
                        "independent_test_seeds":self.test_seeds,
                        "checkpoints":checkpoint_tests},indent=2,allow_nan=False)+"\n",
            encoding="utf-8")
        report={
            **self.protocol,
            "completed_rounds":self.total_rounds,
            "final_cumulative_serialized_uplink_bytes":self.last_bytes,
            "joint_target":{"event_observed":self.first["joint"] is not None,
                            "first_event":self.first["joint"],
                            "right_censored_at_round":None if self.first["joint"] is not None else self.total_rounds,
                            "observed_endpoint_budget_bytes":self.last_bytes,
                            "bytes_to_target":None if self.first["joint"] is None else self.first["joint"]["cumulative_serialized_uplink_bytes"]},
            "load_only_target":{"event_observed":self.first["load_only"] is not None,
                                "first_event":self.first["load_only"],
                                "right_censored_at_round":None if self.first["load_only"] is not None else self.total_rounds,
                                "observed_endpoint_budget_bytes":self.last_bytes,
                                "bytes_to_target":None if self.first["load_only"] is None else self.first["load_only"]["cumulative_serialized_uplink_bytes"]},
            "independent_test_summary":{label:{
                "checkpoint_round_1based":result["checkpoint_round_1based"],
                "joint_successes":result["joint_successes"],
                "load_only_successes":result["load_only_successes"]}
                for label,result in checkpoint_tests.items()}
        }
        (self.root/"bytes_to_target_summary.json").write_text(
            json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        return report
