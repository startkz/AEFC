#!/usr/bin/env python3
"""Independent, fail-closed per-seed/per-episode recovery audit for IEEE39 AC.

This audit produces *new* quasi-static AC evidence, NOT the original
Simulink--Python Fig. 5/6 curves. No plot is inferred from figure pixels.
The 30-step episode is the unit of a trajectory. Training seed is the
independent unit of inference. A censored episode never counts as zero steps.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
import numpy as np

METHODS = {
    "adv": "AEFC-FRL",
    "ordinary": "FedRL-OrdTopK",
    "adv_no_cw": "FedRL-NoCW",
    "dense": "FedRL",
    "dense_cw": "FedRL-NoAdv",
}
SEEDS = tuple(range(80, 90))
EXPECTED = {(mode, seed) for mode in METHODS for seed in SEEDS}
EPISODES, ROUNDS, TESTS = 1000, 200, 10
DWELL, TARGET_PCT, HORIZON = 5, 90.0, 30


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(x, y, name, tol=1.e-6):
    a, b = float(x), float(y)
    require(math.isfinite(a) and math.isfinite(b) and
            abs(a-b) <= tol*max(1., abs(a), abs(b)),
            f"{name}: {a} != {b}")


def recovery_from_trace(trace):
    # Return the start (1-indexed) of the first five consecutive safe
    # and >=90% served-load steps. No recovery => -1 and right-censored.
    count = 0
    for step in trace:
        ok = (bool(step["safe"]) and bool(step["ac_converged"]) and
              float(step["restored_pct"]) >= TARGET_PCT)
        count = count+1 if ok else 0
        if count >= DWELL:
            return int(step["t"]) - DWELL + 1
    return -1


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_one(path, ep_writer, step_writer):
    doc = json.loads(path.read_text(encoding="utf-8"))
    summary = doc["summary"]
    mode = summary["method"]
    seed = int(summary["seed"])
    require((mode, seed) in EXPECTED, f"Unexpected method/seed: {mode}/{seed}")
    require(int(summary["case"]) == 39 and int(summary["clients"]) == 5,
            f"IEEE39 five-client protocol mismatch: {path}")
    require(summary["hetero"] == "dim" and summary["attack"] == "clean",
            "This evidence must be the clean heterogeneous AC control")
    require(int(summary["malicious_clients"]) == 0, "Nonzero malicious count")
    require(summary["weight_cap"] == "None", "Unexpected cap")
    for key,expected in (
        ("train_episodes",EPISODES),("completed_rounds",ROUNDS),
        ("scheduled_rounds",ROUNDS),("train_episode_records",EPISODES),
        ("eval_episodes",TESTS),("steps_per_episode",HORIZON),
        ("fed_sync_interval",5),("batch_size",256),
        ("hidden_size",128),("latent_size",32),
        ("local_fit_steps",5),("sharing_steps",2),
        ("fixed_traffic",0),("record_training_trace",1),
    ):
        require(int(summary[key]) == expected, f"{key} mismatch in {path}")
    close(summary["kappa"],.20,"kappa",1.e-12)
    manifest = path.with_suffix(".manifest.json")
    checkpoint = path.with_suffix(".pt")
    require(manifest.is_file() and checkpoint.is_file(),
            f"Missing manifest or checkpoint for {path}")
    provenance = json.loads(manifest.read_text(encoding="utf-8"))
    require(sha256(path) == provenance["source_json_sha256"],
            f"JSON SHA256 mismatch: {path}")
    require(sha256(checkpoint) == provenance["checkpoint_sha256"],
            f"checkpoint SHA256 mismatch: {path}")
    require(int(provenance["training_episodes_executed"]) == EPISODES,
            "manifest episode count mismatch")
    require(provenance["git_commit"] not in ("unavailable", None, ""),
            "Missing code SHA")
    rounds = doc["rounds"]
    require(len(rounds) == ROUNDS and
            [int(r["round"]) for r in rounds] == list(range(ROUNDS)),
            "Federation round count/order mismatch")
    require(int(sum(r["uplink_bytes"] for r in rounds)) ==
            int(summary["uplink_bytes"]), "uplink accounting mismatch")
    tests = doc["tests"]
    require(len(tests) == TESTS, "Held-out evaluation count mismatch")
    require(sum(int(t["safe_dwell5"]) for t in tests) ==
            summary["safe_dwell_successes"], "Held-out safe dwell mismatch")
    require(len(doc["train_episodes"]) == EPISODES, "Training records not 1000")
    ep_rows = []
    for i,episode in enumerate(doc["train_episodes"], 1):
        require(int(episode["episode"]) == i, "Nonconsecutive episode IDs")
        trace = episode.get("trace")
        require(isinstance(trace, list) and 1 <= len(trace) <= HORIZON,
                f"Missing or invalid trajectory seed={seed} method={mode} episode={i}")
        require(int(episode["steps_executed"]) == len(trace), "steps_executed mismatch")
        require([int(t["t"]) for t in trace] == list(range(1,len(trace)+1)),
                "Nonconsecutive within-episode step index")
        for t in trace:
            require(math.isfinite(float(t["restored_pct"])) and
                    0 <= float(t["restored_pct"]) <= 100.0000001,
                    "Invalid load restoration percentage")
            if not bool(t["ac_converged"]):
                require(not bool(t["safe"]), "Nonconverged power flow marked safe")
            step_writer.writerow({
                "method":METHODS[mode],"mode":mode,"seed":seed,"episode":i,
                "step":t["t"],"restored_pct":t["restored_pct"],
                "safe":int(t["safe"]),"ac_converged":int(t["ac_converged"]),
                "voltage_violation_pu_sum":t["voltage_violation_pu_sum"],
                "thermal_excess_pct_sum":t["thermal_excess_pct_sum"],
            })
        actual = recovery_from_trace(trace)
        require(int(episode["recovery_step"]) == actual,
                f"Recovery mismatch seed={seed} {mode} episode={i}: {episode['recovery_step']} vs {actual}")
        require(int(episode["safe_dwell5"]) == int(actual>=0), "safe-dwell flag mismatch")
        require(int(episode["recovery_reached"]) == int(actual>=0), "reach flag mismatch")
        require(int(episode["censored"]) == int(actual<0), "censoring flag mismatch")
        close(episode["recovery_accuracy_pct"],trace[-1]["restored_pct"],
              "terminal accuracy",1.e-7)
        close(episode["final_restored_pct"],trace[-1]["restored_pct"],
              "terminal load",1.e-7)
        close(episode["average_restored_pct"],
              np.mean([t["restored_pct"] for t in trace]),
              "trajectory mean load",1.e-7)
        require(not (len(trace)<HORIZON and bool(trace[-1]["ac_converged"])),
                "Early termination while AC power flow converged")
        row = {
            "method":METHODS[mode],"mode":mode,"seed":seed,"episode":i,
            "first_safe_dwell_start_step":actual,
            "recovery_reached":int(actual>=0),
            "right_censored":int(actual<0),
            "observed_steps":len(trace),
            "censor_time_steps":len(trace) if actual<0 else "",
            # Restricted step score uses 31 for any failure at the fixed
            # 30-step administrative horizon; separate for physical early exit.
            "restricted_recovery_score":actual if actual>=0 else HORIZON+1,
            "terminal_restored_load_pct":float(episode["recovery_accuracy_pct"]),
            "average_restored_load_pct":float(episode["average_restored_pct"]),
            "any_unsafe":int(episode["any_unsafe"]),
            "thermal_excess_max":float(episode["max_thermal_excess_pct"]),
            "voltage_violation_max":float(episode["max_voltage_violation_pu"]),
            "source_json_sha256":provenance["source_json_sha256"],
            "git_commit":provenance["git_commit"],
        }
        ep_writer.writerow(row)
        ep_rows.append(row)
    require(len(ep_rows)==EPISODES,"Internal audit row count")
    return {
        "mode":mode,"method":METHODS[mode],"seed":seed,"git_commit":provenance["git_commit"],
        "source_json_sha256":provenance["source_json_sha256"],
        "checkpoint_sha256":provenance["checkpoint_sha256"],
        "mean_terminal_restored_pct":float(np.mean([x["terminal_restored_load_pct"] for x in ep_rows])),
        "last100_terminal_restored_pct":float(np.mean([x["terminal_restored_load_pct"] for x in ep_rows[-100:]])),
        "safe_dwell_success_fraction":float(np.mean([x["recovery_reached"] for x in ep_rows])),
        "safe_dwell_success_fraction_last100":float(np.mean([x["recovery_reached"] for x in ep_rows[-100:]])),
        "mean_recovery_step_success_only":(
            float(np.mean([x["first_safe_dwell_start_step"] for x in ep_rows
                         if x["recovery_reached"]])) if any(x["recovery_reached"] for x in ep_rows) else None),
        "mean_restricted_recovery_score":float(np.mean([x["restricted_recovery_score"] for x in ep_rows])),
        "failed_or_censored_count":sum(x["right_censored"] for x in ep_rows),
        "train_episodes":EPISODES,"evaluation_episodes":TESTS,
    }


def csvwriter(fp,fields):
    w=csv.DictWriter(fp,fieldnames=fields)
    w.writeheader()
    return w


def output_tables(out,seeds):
    fields=sorted({k for r in seeds for k in r})
    with (out/"fig56_per_seed.csv").open("w",newline="",encoding="utf-8") as f:
        w=csvwriter(f,fields)
        w.writerows(seeds)
    rows=[]
    for mode,name in METHODS.items():
        subset=[r for r in seeds if r["mode"]==mode]
        require(len(subset)==len(SEEDS),"Missing seeds for "+mode)
        metrics=("mean_terminal_restored_pct","last100_terminal_restored_pct",
                 "safe_dwell_success_fraction","safe_dwell_success_fraction_last100",
                 "mean_restricted_recovery_score","failed_or_censored_count")
        d={"method":name,"mode":mode,"independent_seeds":len(subset)}
        for metric in metrics:
            x=np.array([r[metric] for r in subset],dtype=float)
            rng=np.random.default_rng(20261111+len(rows)*53+len(metric))
            means=x[rng.integers(0,len(x),size=(4000,len(x)))].mean(axis=1)
            d[metric+"_mean"]=float(x.mean())
            d[metric+"_ci95_low"]=float(np.quantile(means,.025))
            d[metric+"_ci95_high"]=float(np.quantile(means,.975))
        rows.append(d)
    with (out/"fig56_seed_summary.csv").open("w",newline="",encoding="utf-8") as f:
        w=csvwriter(f,list(rows[0]))
        w.writerows(rows)
    return rows


def run(root,out):
    root,out=Path(root),Path(out)
    require(root.exists(), f"Missing input root {root}")
    out.mkdir(parents=True,exist_ok=True)
    paths=sorted(p for p in root.rglob("*.json")
                 if not p.name.endswith(".manifest.json") and
                 p.name.endswith(".json"))
    ids=set();seeds=[];errors=[]
    ep_fields=[
        "method","mode","seed","episode","first_safe_dwell_start_step",
        "recovery_reached","right_censored","observed_steps","censor_time_steps",
        "restricted_recovery_score","terminal_restored_load_pct","average_restored_load_pct",
        "any_unsafe","thermal_excess_max","voltage_violation_max",
        "source_json_sha256","git_commit"]
    step_fields=[
        "method","mode","seed","episode","step","restored_pct","safe","ac_converged",
        "voltage_violation_pu_sum","thermal_excess_pct_sum"]
    with (out/"fig56_per_episode.csv").open("w",newline="",encoding="utf-8") as ep_fp, \
         gzip.open(out/"fig56_per_step.csv.gz","wt",newline="",encoding="utf-8",
                   compresslevel=6) as step_fp:
        epw=csvwriter(ep_fp,ep_fields)
        stepw=csvwriter(step_fp,step_fields)
        for p in paths:
            try:
                seedrow=audit_one(p,epw,stepw)
                key=(seedrow["mode"],seedrow["seed"])
                require(key not in ids,"Duplicate run "+str(key))
                ids.add(key)
                seeds.append(seedrow)
            except Exception as exc:
                errors.append({"file":str(p),"reason":str(exc)})
    missing=sorted(EXPECTED-ids)
    unexpected=sorted(ids-EXPECTED)
    commits=sorted({r["git_commit"] for r in seeds})
    if len(commits)!=1:
        errors.append({"reason":"Training runs do not originate from the same code SHA",
                       "commits":commits})
    report={
        "study":"IEEE39 quasi-static AC training convergence; independent supplementary evidence, not native Simulink Fig5/6",
        "expected_runs":len(EXPECTED),"audited_runs":len(seeds),
        "passed":not(errors or missing or unexpected),
        "missing":missing,"unexpected":unexpected,"errors":errors,
        "training_seed_unit":"seed, 80..89",
        "train_episodes_per_seed":EPISODES,"fed_rounds_per_seed":ROUNDS,
        "evaluation_episodes_per_seed":TESTS,
        "recovery_definition":">=90% served load AND AC safe, five consecutive steps, record first step; -1 if not achieved",
        "recovery_censoring":"-1 retained; 31 is a separately labeled restricted score, not measured recovery time",
        "accuracy_definition":"100 * terminal served load / total demand; not a binary success rate",
        "source_git_commits":commits,
        "original_simulink_figures_reproduced":False,
        "not_included":"privileged centrally trained MADDPG; not implemented in AC strict learner",
    }
    (out/"fig56_audit_report.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if not report["passed"]:
        raise ValueError("Fail-closed Fig5/6 evidence audit; details: "+str(out/"fig56_audit_report.json"))
    summary=output_tables(out,seeds)
    # Seed-level mean at each episode, with no inferred intermediate observations.
    bymode=defaultdict(list)
    with (out/"fig56_per_episode.csv").open("r",encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f):
            bymode[(row["mode"],int(row["episode"]))].append(row)
    curve=[]
    for mode in METHODS:
        for ep in range(1,EPISODES+1):
            parts=bymode[(mode,ep)]
            require(len(parts)==len(SEEDS),f"Missing episodes for {mode}, {ep}")
            curve.append({
                "method":METHODS[mode],"mode":mode,"episode":ep,
                "n_independent_seeds":len(parts),
                "mean_terminal_restored_load_pct":float(np.mean([
                    float(x["terminal_restored_load_pct"]) for x in parts])),
                "mean_restricted_recovery_score":float(np.mean([
                    float(x["restricted_recovery_score"]) for x in parts])),
                "safe_dwell_fraction":float(np.mean([
                    int(x["recovery_reached"]) for x in parts])),
                "n_censored":sum(int(x["right_censored"]) for x in parts),
            })
    with (out/"fig56_per_episode_seed_mean.csv").open("w",newline="",encoding="utf-8") as f:
        w=csvwriter(f,list(curve[0]))
        w.writerows(curve)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for field,ylabel,name in (
            ("mean_restricted_recovery_score","Restricted recovery-step score (failures = 31)","fig5_ieee39_ac_supplement.png"),
            ("mean_terminal_restored_load_pct","Terminal served load (%)","fig6_ieee39_ac_supplement.png"),
        ):
            fig,ax=plt.subplots(figsize=(8.2,4.5))
            for mode,label in METHODS.items():
                pts=[r for r in curve if r["mode"]==mode]
                values=np.array([r[field] for r in pts])
                # Plot only visual smoothing; raw 50,000 episode rows remain untouched.
                smooth=np.convolve(np.pad(values,(15,15),mode="edge"),
                                   np.ones(31)/31,mode="valid")
                ax.plot(np.arange(1,EPISODES+1),smooth,label=label,linewidth=1.5)
            ax.set_xlabel("Training episode")
            ax.set_ylabel(ylabel)
            ax.set_title("IEEE39 quasi-static AC (not original Simulink figure)")
            ax.grid(alpha=.2)
            ax.legend(fontsize=8,ncol=2)
            fig.tight_layout()
            fig.savefig(out/name,dpi=200)
            plt.close(fig)
    except ImportError:
        report["plotting"]="matplotlib unavailable, tables audited"
    (out/"fig56_audit_report.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return {"passed":True,"audited_runs":len(seeds),"data_rows":len(SEEDS)*len(METHODS)*EPISODES,
            "one_source_commit":commits[0],"methods":[x["method"] for x in summary]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.root,a.out),indent=2))
