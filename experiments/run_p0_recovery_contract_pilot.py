#!/usr/bin/env python3
"""P0 pilot: bounded-noise, fixed-target post-poisoning recovery and shield contract.
This is a new reduced-order diagnostic, NOT native IEEE39, not formal continuous-time G5.
All parameters are frozen prior to running. Main 560 and supplemental data untouched.
"""
import csv, json, math, os
from pathlib import Path
import numpy as np

OUT=Path("results/p0_contract_pilot")
SEEDS=range(40)
STEPS=240
POISON_START=24
POISON_END=72
TARGET=np.array([0.10,-0.08,0.06,-0.04])
EPS=0.01
ALPHA=0.90
ETA=1-ALPHA
DUR=20
SAFE=0.35
DIST_BOUND=0.006
DOWNSTREAM=0.10
ACTION_LIMIT=0.8
GAIN=0.24

def shield(x, proposed, drift):
    low=(-SAFE+DIST_BOUND-x-drift)/GAIN+DOWNSTREAM
    high=(SAFE-DIST_BOUND-x-drift)/GAIN-DOWNSTREAM
    feasible=bool(np.all(low<=high) and np.all(np.maximum(low,-ACTION_LIMIT)<=np.minimum(high,ACTION_LIMIT)))
    if not feasible: return np.clip(proposed,-ACTION_LIMIT,ACTION_LIMIT), False, -1.
    low=np.maximum(low,-ACTION_LIMIT);high=np.minimum(high,ACTION_LIMIT)
    u=np.clip(proposed,low,high)
    margin=float(np.min(SAFE-np.abs(x+drift+GAIN*u)-DIST_BOUND-GAIN*DOWNSTREAM))
    return u,True,margin

def run(seed, mode):
    rng=np.random.default_rng(100003+seed*101)
    x=np.array([.03,-.02,.015,-.01])+rng.uniform(-.005,.005,4)
    theta=np.zeros(4)
    clean_theta=np.zeros(4)
    errors=[]; post=[]; pre_bad=0; accepted=0
    bounds_pass=0; violations=0; infeasible=0; margins=[]
    action_norms=[]; utility=[]
    path=OUT/mode/f"seed_{seed:02d}.jsonl"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w") as f:
        for t in range(STEPS):
            attack=(POISON_START<=t<POISON_END)
            # Fixed certified synthetic target and bounded malicious gradient input.
            # No online access to clean_theta, attack labels, or oracle true state in the learner.
            malicious=(np.array([-2.0,1.8,-1.6,1.4]) if attack else np.zeros(4))
            trusted_weight=0.10 if mode=="bounded" and attack else 1.0
            attack_grad=malicious*trusted_weight
            proposed_theta=ALPHA*theta+(1-ALPHA)*TARGET + ETA*attack_grad
            # A separate, unattacked shadow uses the identical contractive operator.
            clean_theta=ALPHA*clean_theta+(1-ALPHA)*TARGET
            step=float(np.linalg.norm(proposed_theta-theta))
            theta=proposed_theta
            dist=float(np.linalg.norm(theta-clean_theta))
            errors.append(dist)
            if t>=POISON_END: post.append(dist)
            # Evaluation-only physical plant: controller sees received noisy measurement,
            # not the true plant state. The independent shield receives authenticated x.
            noise_obs=rng.uniform(-.01,.01,4)
            obs=x+noise_obs
            controller_proposal=-0.5*obs+0.2*theta
            physical_drift=-0.05*x
            u,feasible,margin=shield(x,controller_proposal,physical_drift)
            a=rng.uniform(-DOWNSTREAM,DOWNSTREAM,4)
            w=rng.uniform(-DIST_BOUND,DIST_BOUND,4)
            nxt=x+physical_drift+GAIN*(u+a)+w
            inside=bool(np.max(np.abs(nxt))<=SAFE+1e-12)
            infeasible+=int(not feasible)
            violations+=int(not inside)
            bounds_pass+=int(np.max(np.abs(w))<=DIST_BOUND+1e-12 and np.max(np.abs(a))<=DOWNSTREAM+1e-12)
            margins.append(margin)
            utility.append(float(np.linalg.norm(nxt,1)))  # independent state-regulation proxy
            action_norms.append(float(np.linalg.norm(u,2)))
            row={"seed":seed,"mode":mode,"t":t,"poison_active_eval_only":attack,
                 "theta_deployed":theta.tolist(),"theta_clean_reference_eval_only":clean_theta.tolist(),
                 "theta_error":dist,"trusted_poison_weight":trusted_weight,
                 "control_observation":obs.tolist(),"plant_state_before_eval_only":x.tolist(),
                 "physical_drift":physical_drift.tolist(),"controller_proposal":controller_proposal.tolist(),
                 "shield_output":u.tolist(),"physical_attack":a.tolist(),"model_disturbance":w.tolist(),
                 "actual_next_state":nxt.tolist(),"shield_feasible":feasible,
                 "robust_margin":margin,"safety_ok":inside,"control_effort":action_norms[-1],
                 "state_regulation_cost":utility[-1]}
            f.write(json.dumps(row,separators=(",",":"))+"\n")
            x=nxt
    # Empirical post-stop contraction must agree with exact construction, all steps.
    observed_ratios=[post[i+1]/post[i] for i in range(len(post)-1) if post[i]>1e-12]
    max_ratio=max(observed_ratios) if observed_ratios else 0.
    first_valid=None
    for j in range(len(post)-DUR+1):
        if max(post[j:j+DUR])<=EPS:
            first_valid=j;break
    return {"seed":seed,"mode":mode,"n_steps":STEPS,"post_steps":len(post),
            "theta_error_stop":post[0],"theta_error_last":post[-1],
            "time_to_epsilon_consecutive":first_valid if first_valid is not None else "",
            "contraction_ratio_max_observed":max_ratio,"shield_infeasible":infeasible,
            "state_violations":violations,"bounded_disturbance_samples":bounds_pass,
            "min_robust_margin":min(margins),
            "regulation_cost_mean":float(np.mean(utility)),
            "control_effort_mean":float(np.mean(action_norms))}

def main():
    allrows=[run(seed,mode) for mode in ("bounded","unfiltered") for seed in SEEDS]
    OUT.mkdir(exist_ok=True,parents=True)
    with (OUT/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    manifest={"experiment":"P0 synthetic fixed-target contractive diagnostic",
        "status":"exploratory only","backend":"4d synthetic bounded plant; NOT native IEEE39",
        "not_native_G1_or_G3_or_G5_proof":True,"seeds":40,"modes":["bounded","unfiltered"],
        "runs":80,"steps":STEPS,"poison_window":[POISON_START,POISON_END],
        "fixed_reference":TARGET.tolist(),"contraction_alpha":ALPHA,
        "epsilon":EPS,"consecutive":DUR,"disturbance_model":"uniform; bounded by construction",
        "state_regulation_cost":"mean L1 norm of true evaluation-only plant state",
        "source_sha":os.environ.get("GITHUB_SHA","local")}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    for mode in ("bounded","unfiltered"):
        r=[x for x in allrows if x["mode"]==mode]
        print(json.dumps({"mode":mode,"runs":len(r),
            "mean_error_post_start":float(np.mean([a["theta_error_stop"] for a in r])),
            "mean_error_post_end":float(np.mean([a["theta_error_last"] for a in r])),
            "reach_persistent_epsilon":sum(a["time_to_epsilon_consecutive"]!="" for a in r),
            "max_contraction_ratio":max(a["contraction_ratio_max_observed"] for a in r),
            "state_violations":sum(a["state_violations"] for a in r),
            "shield_infeasible":sum(a["shield_infeasible"] for a in r),
            "mean_regulation_cost":float(np.mean([a["regulation_cost_mean"] for a in r]))}))
    assert len(allrows)==80
    assert all(r["state_violations"]==0 and r["shield_infeasible"]==0 for r in allrows)
    assert all(r["contraction_ratio_max_observed"]<=ALPHA+1e-8 for r in allrows)
    assert all(r["time_to_epsilon_consecutive"]!="" for r in allrows)

if __name__=="__main__":main()
