#!/usr/bin/env python3
"""P0 contract verification in an explicit bounded discrete-time 4-state plant.

This is NOT a proof of native IEEE39 continuous-time G5 or original AEFC G3.
A trusted incident-clearance signal is an explicit recovery-mode assumption.
All attack/plant disturbances pre-generated per seed, shared across methods.
"""
import csv, json, hashlib, os
from pathlib import Path
import numpy as np

OUT=Path("results/p0_bounded_contract")
N=40
T=240
STOP=72
ALPHA=0.90
EPS=0.01
PERSIST=20
G=0.24
L=0.35
U=0.80
AU=0.10
W=0.006
DT=1.0
A=np.array([[-.11,.03,0,0],[.02,-.08,.02,0],[0,.02,-.10,.03],[0,0,.02,-.09]])
BIAS=np.array([.09,-.08,.075,-.07])
MODES=("no_cleanup","certified_anchor","certified_anchor_residual")

def run(seed,mode):
    rng=np.random.default_rng(240000+seed)
    x=rng.normal(0,.025,4)
    theta=np.zeros(4)
    anchor=np.zeros(4)
    pre_g=rng.normal(.010,.002,(T,4)) + np.array([.004,-.003,.002,-.002])
    post_a=rng.uniform(-AU,AU,(T,4))
    w=rng.uniform(-W,W,(T,4))
    residual=rng.uniform(-.0002,.0002,(T,4))
    path=OUT/mode
    path.mkdir(parents=True,exist_ok=True)
    errors=[]
    after_errors=[]
    infeasible=violations=contract_fail=coverage_fail=0
    input_violations=step_contract_violations=0
    costs=control_cost=0.0
    action_overrides=0
    with (path/f"seed_{seed:02d}.jsonl").open("w") as fo:
        for t in range(T):
            active=(24<=t<STOP)
            cleaned=(t>=STOP) # externally certified clearance, NOT inferred from attacker labels
            before=theta.copy()
            if not cleaned:
                # Chosen fixed, bounded adversarially biased update;
                # identical exogenous sequence across all modes.
                theta=theta+pre_g[t]
            elif mode=="certified_anchor":
                theta=ALPHA*theta+(1-ALPHA)*anchor
            elif mode=="certified_anchor_residual":
                theta=ALPHA*theta+(1-ALPHA)*anchor+residual[t]
            else:
                theta=theta+np.zeros(4)
            e=float(np.linalg.norm(theta-anchor))
            eold=float(np.linalg.norm(before-anchor))
            if cleaned:
                budget=0.0 if mode=="certified_anchor" else (.0004 if mode=="certified_anchor_residual" else None)
                if budget is not None and e>ALPHA*eold+budget+1e-12:
                    contract_fail+=1
                after_errors.append(e)
            else:
                budget=None
            errors.append(e)
            drift=A@x+(BIAS if 18<=t<34 else 0.)
            # Controller policy & robust one-step safety interval.
            proposed=-.65*x + 1.5*theta
            lower=np.maximum((-L+W-x-drift)/G+AU,-U+AU)
            upper=np.minimum((L-W-x-drift)/G-AU,U-AU)
            feas=bool(np.all(lower<=upper))
            if not feas:
                infeasible+=1
                u=np.clip(proposed,-U+AU,U-AU)
            else:
                u=np.clip(proposed,lower,upper)
            if np.linalg.norm(u-proposed)>1e-10:action_overrides+=1
            # Actual downstream attack is bounded at EVERY step, not sampled Gaussian.
            au=post_a[t] if active else np.zeros(4)
            executed=u+au
            xnext=x+drift+G*executed+w[t]
            bound_w=float(np.max(np.abs(w[t])))
            if bound_w>W+1e-12:coverage_fail+=1
            if np.max(np.abs(executed))>U+1e-12: input_violations+=1
            if np.max(np.abs(xnext))>L+1e-12: violations+=1
            # Valid when state measured exactly, disturbances bounded and interval feasible.
            if feas and np.max(np.abs(xnext))>L+1e-11:step_contract_violations+=1
            costs+=float(np.dot(xnext,xnext))*DT
            control_cost+=float(np.dot(executed,executed))*DT
            line={"seed":seed,"mode":mode,"t":t,"attack_active":active,
                  "trusted_cleanup_signal":cleaned,"true_benign_state_evaluation_only":xnext.tolist(),
                  "trusted_anchor":anchor.tolist(),"theta_deployed":theta.tolist(),
                  "parameter_error":e,"previous_parameter_error":eold,
                  "samplewise_contraction_factor_assumed":ALPHA if cleaned and budget is not None else None,
                  "contraction_residual_budget":budget,
                  "contract_feasible":feas,"actuation_proposal":proposed.tolist(),
                  "robust_action":u.tolist(),"downstream_attack":au.tolist(),
                  "actual_action":executed.tolist(),
                  "plant_noise_inf":bound_w,"sample_safe":bool(np.max(np.abs(xnext))<=L+1e-12)}
            fo.write(json.dumps(line,separators=(",",":"))+"\n")
            x=xnext
    achieved=None
    # first *new* time below epsilon, and continuous persistence; censor tail
    if after_errors[0]>EPS:
        for j in range(1,len(after_errors)-PERSIST+1):
            if all(a<=EPS for a in after_errors[j:j+PERSIST]):
                achieved=j;break
    ans={"seed":seed,"mode":mode,"total_steps":T,"cleanup_start_step":STOP,
         "parameter_distance_at_cleanup":after_errors[0],"parameter_distance_end":after_errors[-1],
         "new_finite_epsilon_correction":achieved is not None,
         "time_to_epsilon_post_cleanup":achieved,
         "correction_right_censored":achieved is None,
         "max_post_cleanup_one_step_ratio":max((b/a for a,b in zip(after_errors[:-1],after_errors[1:]) if a>1e-9),default=None),
         "contraction_bound_violations":contract_fail,
         "robust_qp_infeasible_steps":infeasible,
         "bounded_disturbance_failures":coverage_fail,
         "input_bound_violations":input_violations,
         "sampled_plant_violations":violations,"robust_implication_failures":step_contract_violations,
         "shield_intervention_count":action_overrides,
         "integrated_physical_state_cost":costs,
         "integrated_total_actuation_cost":control_cost,
         "backend":"discrete_bounded_4state_contract"}
    (path/f"seed_{seed:02d}.summary.json").write_text(json.dumps(ans,indent=2)+"\n")
    return ans

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    summaries=[run(seed,mode) for mode in MODES for seed in range(N)]
    with (OUT/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]))
        w.writeheader();w.writerows(summaries)
    m={"experimental_status":"genuine_executed_new_mechanism",
       "backend":"discrete_bounded_4state_contract","not_native_ieee39":True,
       "does_not_prove_continuous_CBF_G5":True,
       "does_not_validate_old_AEFC_G3":True,
       "full_state_measured_without_uncertainty":True,
       "trusted_incident_clearance_assumed":True,
       "config":{"seed_count":N,"steps":T,"cleanup":STOP,"alpha":ALPHA,
                 "epsilon":EPS,"persistence":PERSIST,"state_limit":L,
                 "action_limit":U,"post_shield_attack_bound":AU,"state_disturbance_bound":W},
       "methods":MODES,"episodes":len(summaries),
       "commit_sha":os.environ.get("GITHUB_SHA","LOCAL")}
    (OUT/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    for mode in MODES:
        subset=[r for r in summaries if r["mode"]==mode]
        print(mode,json.dumps({"corrected":sum(r["new_finite_epsilon_correction"] for r in subset),
             "mean_end_dist":float(np.mean([r["parameter_distance_end"] for r in subset])),
             "mean_cost":float(np.mean([r["integrated_physical_state_cost"] for r in subset])),
             "sampled_violations":sum(r["sampled_plant_violations"] for r in subset),
             "infeasible":sum(r["robust_qp_infeasible_steps"] for r in subset),
             "contract_violation":sum(r["contraction_bound_violations"] for r in subset)}))
    assert all(r["contraction_bound_violations"]==0 for r in summaries)
    assert all(r["robust_implication_failures"]==0 for r in summaries)

if __name__=="__main__":
    main()
