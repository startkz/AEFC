#!/usr/bin/env python3
"""P0 exploratory, oracle-free-learning-path shadow study on REDUCED-ORDER CPS.
Not an IEEE39 run, full G3 proof, or robust CBF-QP/continuous-time G5 audit.
Seeds and settings are fixed before viewing results; Main 560/720 untouched.
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from aefc.security import (AdaptConfig, Evidence, GateConfig, PATBUConfig,
                           ProvenanceAwareTemporalBelief, RiskAwareRecoveryGate,
                           RobustBoxShield, ShieldConfig, TrustGatedAdaptation)
from aefc.federation import robust_sparse_aggregate
from aefc.surrogate import ReducedOrderCPS
from aefc.attacks import AttackConfig, active, observation_attack, poison_update, post_shield_attack

CONFIG = Path("configs/joint20.json")
OUT = Path("results/p0_shadow_reduced")
SEEDS = tuple(range(40))
CONDITIONS = ("knowledge", "joint")
STEPS = 240
EPS = 0.01
PERSIST = 20


def make_items(cfg):
    return (ProvenanceAwareTemporalBelief(4, PATBUConfig(**cfg["patbu"], trim_f=cfg["byzantine_clients"])),
            RiskAwareRecoveryGate(GateConfig(**cfg["gate"])),
            TrustGatedAdaptation(4, AdaptConfig(**cfg["adaptation"])))


def evaluate_step(belief, trust, adapter, gate, agg, obs):
    """Online controls read their own belief, trust, and received observations.
    Deliberately no labels, clean references, clean target, or true state.
    """
    prop = -.55 * belief + 1.5 * adapter.deployed
    safety_gap = max(0.0, float(np.max(np.abs(belief + .24 * prop)))-.30)
    rec_gap = max(0.0, float(np.max(np.abs(belief)))-.08)
    unc = min(1.0, float(np.linalg.norm(obs-belief)))
    allowed, risk = gate.assess(safety_gap, rec_gap, unc, trust)
    if not allowed:
        prop = -.35 * belief
    before = adapter.deployed.copy()
    candidate = adapter.propose(agg, trust)
    vb = float(np.linalg.norm(belief)+.08*np.linalg.norm(before))
    va = float(np.linalg.norm(belief)+.08*np.linalg.norm(candidate))
    _, diag = adapter.deploy(candidate, trust, allowed, vb, va)
    step_norm = float(np.linalg.norm(adapter.deployed-before))
    bound = min(float(adapter.config.eta)*trust*float(adapter.config.clip_norm),
                float(adapter.config.trust_region))
    assert step_norm <= bound+1e-10, (step_norm, bound)
    return np.asarray(prop), allowed, risk, bool(diag["accepted"]), step_norm, bound


def run_one(seed, condition, cfg, config_hash):
    root = OUT/condition
    root.mkdir(parents=True, exist_ok=True)
    trace_file = root/f"seed_{seed:02d}.jsonl"
    rng = np.random.default_rng(700013 + seed*1013)
    plant = ReducedOrderCPS(dim=4, seed=seed+33000)
    plant.reset()
    online, gate_online, adapt_online = make_items(cfg)
    shadow, gate_shadow, adapt_shadow = make_items(cfg)
    shield = RobustBoxShield(ShieldConfig(**dict(cfg["shield"],
                                                   state_limit=cfg["safe_state_limit"])))
    atk = AttackConfig(**cfg["attack"])
    byz = int(cfg["byzantine_clients"])
    clients = int(cfg["clients"])
    max_error = max_legacy_error = max_target_error = 0.0
    peak_attack_error = 0.0
    bound_checks = violations = infeasible = uncovered_noise = action_excess = 0
    naccepted = nrejected = 0
    accept_steps = []
    errors_post = []
    recovery_times = []
    true_violations = 0
    legacy_ref = np.zeros(4)
    max_noise = 0.0
    with trace_file.open("w", encoding="utf8") as fp:
        for t in range(STEPS):
            # Both shadow and attacked update see identical, matched PLANT PATH.
            # Clean evidence/observation are only used in offline shadow.
            x_before = plant.x.copy()
            clean_obs = plant.clean_observation()
            obs = clean_obs + (observation_attack(4,t,rng,atk,True)
                               if condition == "joint" else np.zeros(4))
            honest_updates, attacked_updates = [], []
            shadow_evidence, online_evidence = [], []
            for j in range(clients):
                clean_g = .65*x_before+.15*rng.normal(size=4)
                clean_ev = -.55*x_before+.08*rng.normal(size=4)
                is_comp = j<byz and active(t,atk)
                report_g = poison_update(clean_g,t,rng,atk,is_comp)
                report_ev = (2.8*clean_ev+.6) if is_comp else clean_ev.copy()
                # All reports are syntactically valid: NO privileged true-byzantine flags.
                # Timestamps remain protocol metadata, not certified creation times.
                ts = t-atk.stale_delay if is_comp else t
                online_evidence.append(Evidence(report_ev,f"client-{j}",ts,1,f"r{t}",True))
                shadow_evidence.append(Evidence(clean_ev,f"client-{j}",t,1,f"r{t}",True))
                honest_updates.append(clean_g)
                attacked_updates.append(report_g)
            b, detail = online.update(obs,online_evidence,t)
            b0, d0 = shadow.update(clean_obs,shadow_evidence,t)
            trust = float(detail["trust"]); clean_trust = float(d0["trust"])
            if not (np.isfinite(b).all() and np.isfinite(b0).all()):
                raise RuntimeError(f"Non-finite belief at {seed}, {t}")
            legacy_ref = .72*legacy_ref+.20*clean_obs+.08*np.mean(
                np.stack([ev.value for ev in shadow_evidence]),axis=0)
            err = float(np.linalg.norm(b-b0))
            legacy_err = float(np.linalg.norm(b-legacy_ref))
            max_error = max(max_error,err); max_legacy_error=max(max_legacy_error,legacy_err)
            if active(t,atk): peak_attack_error=max(peak_attack_error,err)
            attacked_agg,_ = robust_sparse_aggregate(attacked_updates,f=byz,k=cfg["common_support_k"])
            clean_agg,_ = robust_sparse_aggregate(honest_updates,f=byz,k=cfg["common_support_k"])
            prop, allowed, risk, acc, step_size, bound = evaluate_step(
                b,trust,adapt_online,gate_online,attacked_agg,obs)
            _, shadow_allowed, _, shadow_acc, _, _ = evaluate_step(
                b0,clean_trust,adapt_shadow,gate_shadow,clean_agg,clean_obs)
            if acc: naccepted+=1; accept_steps.append(t)
            else: nrejected+=1
            target_error = float(np.linalg.norm(adapt_online.deployed-adapt_shadow.deployed))
            max_target_error=max(max_target_error,target_error)
            if t >= atk.end: errors_post.append(target_error)
            drift = plant.drift()
            u, sh = shield.project(x_before,prop,drift)
            au = post_shield_attack(4,t,rng,atk, condition=="joint")
            executed = u+au
            x_after = plant.step(executed)
            disturbance = x_after-x_before-drift-.24*executed
            noise_inf = float(np.max(np.abs(disturbance)))
            max_noise=max(max_noise,noise_inf)
            if noise_inf>cfg["shield"]["state_disturbance_budget"]+1e-12: uncovered_noise+=1
            if not sh["feasible"]: infeasible+=1
            if np.max(np.abs(executed))>cfg["shield"]["action_limit"]+1e-12: action_excess+=1
            true_violations += int(not plant.safe())
            # A nonnegative *reported* robust margin is not a certified forward invariant.
            errbound = (float(np.linalg.norm(obs-clean_obs)) if condition=="joint" else 0.0)
            bound_checks += int(np.isfinite(errbound))
            row = {"seed":seed,"condition":condition,"t":t,"attack_active":bool(active(t,atk)),
                   "input_no_byzantine_identity":True,"input_no_clean_belief":True,
                   "same_operator_shadow":True,"belief_state":b.tolist(),"shadow_belief_state":b0.tolist(),
                   "legacy_reference_state":legacy_ref.tolist(),"belief_error_same_operator":err,
                   "belief_error_legacy":legacy_err,"trust_online":trust,"trust_shadow":clean_trust,
                   "gate_online":bool(allowed),"gate_shadow":bool(shadow_allowed),"risk_online":float(risk),
                   "theta_online":adapt_online.deployed.tolist(),
                   "theta_clean_shadow":adapt_shadow.deployed.tolist(),
                   "target_parameter_error":target_error,"adapt_accepted":bool(acc),
                   "shadow_adapt_accepted":bool(shadow_acc),"step_norm":step_size,"step_bound":bound,
                   "shield_feasible_reported":bool(sh["feasible"]),
                   "shield_robust_margin_reported":float(sh["robust_margin"]),
                   "state_true_evaluation_only":x_after.tolist(),
                   "disturbance_inf_evaluation_only":noise_inf,
                   "action_executed":executed.tolist(),"safe_evaluation_only":bool(plant.safe())}
            fp.write(json.dumps(row,separators=(",",":"))+"\n")
    # Define run-wise finite-epsilon correction conservatively: 20 successive time steps
    # below epsilon after poison stops. Does not establish a global contraction theorem.
    achieved=None
    for idx in range(len(errors_post)-PERSIST+1):
        if all(v<=EPS for v in errors_post[idx:idx+PERSIST]):
            achieved=idx
            break
    postaccept = [t for t in accept_steps if t>=atk.end]
    complete_intervals=[b-a for a,b in zip(postaccept,postaccept[1:])]
    tail_censored=(STEPS-1-postaccept[-1]) if postaccept else STEPS-atk.end
    summary={"seed":seed,"condition":condition,"steps":STEPS,"attack_end_exclusive":atk.end,
             "max_belief_error_same_operator":max_error,"max_belief_error_legacy":max_legacy_error,
             "max_belief_error_during_attack":peak_attack_error,
             "max_clean_shadow_policy_distance":max_target_error,
             "post_attack_initial_policy_distance":errors_post[0],
             "post_attack_final_policy_distance":errors_post[-1],
             "time_to_epsilon_20consecutive":achieved,
             "time_to_epsilon_censored":achieved is None,
             "accepted_total":naccepted,"rejected_total":nrejected,
             "accepted_post_attack":len(postaccept),
             "max_complete_accept_interval":max(complete_intervals) if complete_intervals else None,
             "tail_rejection_censored":tail_censored,
             "robust_shield_infeasible_steps":infeasible,"disturbance_budget_exceed_steps":uncovered_noise,
             "action_limit_exceed_steps":action_excess,"sampled_state_violations":true_violations,
             "disturbance_inf_max":max_noise,
             "main_ieee39_reused":False,"backend":"reduced_order_shadow_exploration"}
    (root/f"seed_{seed:02d}.summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


def main():
    cfg=json.loads(CONFIG.read_text())
    cfg_id=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    all_rows=[]
    for condition in CONDITIONS:
        for seed in SEEDS:
            all_rows.append(run_one(seed,condition,cfg,cfg_id))
    with (OUT/"summary.csv").open("w",newline="") as fp:
        keys=list(all_rows[0].keys())
        w=csv.DictWriter(fp,fieldnames=keys);w.writeheader();w.writerows(all_rows)
    report={"status":"completed","backend":"reduced_order_shadow_exploration",
            "not_a_native_ieee39_test":True,"not_formal_G1_G3_G5_validation":True,
            "commit_sha":os.environ.get("GITHUB_SHA","LOCAL"),
            "config_sha256":cfg_id,"episodes":len(all_rows),"steps":STEPS,
            "seeds":len(SEEDS),"conditions":CONDITIONS,
            "online_inputs":"received observation, all syntactically valid reports, local timestamps",
            "shadow_inputs":"clean observations/reports; held outside live controller",
            "g1_reference":"same operator and matched actual plant path",
            "g3_target":"independent clean-knowledge shadow; dynamic reference, not theorem fixed point",
            "g5_scope":"sampled reduced-order box shield; Gaussian state disturbance unbounded",
            "epsilon":EPS,"persistence_steps":PERSIST}
    (OUT/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    for condition in CONDITIONS:
        subset=[r for r in all_rows if r["condition"]==condition]
        print(json.dumps({"condition":condition,"n":len(subset),
                          "same_operator_belief_error_mean":float(np.mean([r["max_belief_error_same_operator"] for r in subset])),
                          "final_clean_parameter_error_mean":float(np.mean([r["post_attack_final_policy_distance"] for r in subset])),
                          "epsilon_corrected_20steps":sum(r["time_to_epsilon_20consecutive"] is not None for r in subset),
                          "post_attack_accept_mean":float(np.mean([r["accepted_post_attack"] for r in subset])),
                          "noise_budget_exceed_total":sum(r["disturbance_budget_exceed_steps"] for r in subset),
                          "shield_infeasible_total":sum(r["robust_shield_infeasible_steps"] for r in subset),
                          "state_violation_total":sum(r["sampled_state_violations"] for r in subset)}))


if __name__=="__main__":
    main()
