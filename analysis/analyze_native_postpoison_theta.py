#!/usr/bin/env python3
"""Independent 120-run native post-poisoning archive audit and descriptive analysis.
Runs only after both GitHub native jobs report success; never edits Main results.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np

SRC=Path("results/p0_native_postpoison_download")
DST=Path("results/p0_native_postpoison")
DST.mkdir(parents=True,exist_ok=True)
MAIN=Path("results/ieee39_joint20/summary.csv")
SCENARIOS={"knowledge":2,"joint":4}
METHODS=("FedRL","AEFC-no-TGOPA","AEFC-Full")
D=4; STEPS=220; POST_START=44; EPS=1e-3; HOLD=20
metrics=("max_policy_drift","max_belief_distortion","min_native_margin")
baseline={(r["scenario"],r["method"],int(r["seed"])):r
          for r in csv.DictReader(MAIN.open())}
aggregates=[]
deviations=[]
audit=[]
allpair={}
for scenario,code in SCENARIOS.items():
    folders=list(SRC.glob("AEFC-P0-native-parameter-"+scenario+"-*"))
    if len(folders)!=1: raise AssertionError((scenario,"artifact folder count",len(folders)))
    folder=folders[0]
    sub=folder/"summary.csv"
    if not sub.exists(): raise AssertionError(sub)
    rows=list(csv.DictReader(sub.open()))
    if len(rows)!=len(METHODS)*20: raise AssertionError(("summary length",scenario,len(rows)))
    for row in rows:
        method=row["method"];seed=int(row["seed"]); assert method in METHODS
        assert row["scenario"]==scenario
        j=folder/method/f"seed_{seed:02d}.jsonl"
        summ=folder/method/f"seed_{seed:02d}.summary.json"
        if not j.exists() or not summ.exists():raise AssertionError(("missing",j,summ))
        samples=[json.loads(x) for x in j.read_text().splitlines() if x.strip()]
        if len(samples)!=STEPS:raise AssertionError((j,"step count",len(samples)))
        if not all(len(x["deployed_theta"])==4 and len(x["clean_shadow_theta"])==4 for x in samples):
            raise AssertionError((j,"theta dimensions"))
        params=np.asarray([x["deployed_theta"] for x in samples],dtype=float)
        shadow=np.asarray([x["clean_shadow_theta"] for x in samples],dtype=float)
        errors=np.linalg.norm(params-shadow,axis=1)
        logged=np.asarray([x["theta_reference_error"] for x in samples],dtype=float)
        if np.max(np.abs(errors-logged))>1e-10:raise AssertionError((j,"error trajectory"))
        steps=np.linalg.norm(np.diff(np.vstack((np.zeros((1,4)),params)),axis=0),axis=1)
        logged_steps=np.asarray([x["step_norm"] for x in samples])
        if np.max(np.abs(steps-logged_steps))>1e-9:raise AssertionError((j,"step norm"))
        if np.max(errors[:15])>1e-9:raise AssertionError((j,"pre-attack shadow mismatch"))
        post=errors[POST_START:]
        if len(post)<120:raise AssertionError((j,"short post window"))
        first=None
        for i in range(len(post)-HOLD+1):
            if np.all(post[i:i+HOLD]<=EPS):
                first=i;break
        expected=float(row["theta_error_at_stop"])
        if abs(expected-post[0])>1e-10 or abs(float(row["theta_error_at_end"])-post[-1])>1e-10:
            raise AssertionError((j,"summary mismatch"))
        if bool(first is not None)!=bool(str(row["time_to_epsilon20"]).strip().lower() not in ("","nan")):
            raise AssertionError((j,"epsilon summary mismatch"))
        accepted=np.asarray([bool(x["adapt_accepted"]) for x in samples])
        if int(accepted[POST_START:].sum())!=int(row["post_updates_accepted"]):
            raise AssertionError((j,"accept count"))
        first73=samples[:73]
        base=baseline[(scenario,method,seed)]
        first_metrics={
            "max_policy_drift":max(x["policy_drift"] for x in first73),
            "max_belief_distortion":max(x["belief_distortion"] for x in first73),
            "min_native_margin":min(1-max(abs(z) for z in x["observation_normalized"]) for x in first73)
        }
        for m in metrics:
            deviations.append(abs(float(base[m])-float(first_metrics[m])))
        audit.append({"scenario":scenario,"method":method,"seed":seed,
                      "samples":len(samples),"max_theta_error_check":float(np.max(np.abs(errors-logged))),
                      "max_step_norm_check":float(np.max(np.abs(steps-logged_steps))),
                      "baseline_three_field_max_diff":max(abs(float(base[m])-first_metrics[m]) for m in metrics)})
        accepted_post=np.where(accepted[POST_START:])[0]
        accept_gaps=np.diff(accepted_post) if len(accepted_post)>1 else np.array([])
        ratios=post[1:]/np.maximum(post[:-1],1e-15)
        meaningful=post[:-1]>EPS
        rate=float(np.max(ratios[meaningful])) if meaningful.any() else float("nan")
        key=(scenario,method,seed)
        allpair[key]={
            "scenario":scenario,"method":method,"seed":seed,"post_steps":len(post),
            "theta_error_before_attack":float(errors[14]),
            "theta_error_at_stop":float(post[0]),
            "theta_error_final":float(post[-1]),
            "theta_error_max_after":float(np.max(post)),
            "exposed_at_stop":int(post[0]>EPS),
            "attained20":int(first is not None),
            "corrected_after_attack":int(post[0]>EPS and first is not None),
            "time_to_epsilon20":first if first is not None else "",
            "post_accepted":int(accepted[POST_START:].sum()),
            "post_rejected":int((~accepted[POST_START:]).sum()),
            "max_complete_accept_interval":int(np.max(accept_gaps)) if len(accept_gaps) else "",
            "tail_censored_steps":int(len(post)-1-accepted_post[-1]) if len(accepted_post) else len(post),
            "post_nondecrease_steps":int((np.diff(post)>1e-10).sum()),
            "max_observed_error_ratio_above_epsilon":rate,
            "mean_native_response_norm":float(np.mean([np.linalg.norm(x["observation_normalized"],ord=1) for x in samples])),
            "sampled_safety_violations":int(sum(not x["safe_native_envelope"] for x in samples)),
        }
if len(audit)!=120 or len(deviations)!=360:raise AssertionError("unexpected audit count")
maxdiff=max(deviations)
if maxdiff>1e-8:raise AssertionError(("original Main first-73 reproduction failed",maxdiff))
data=list(allpair.values())
with (DST/"seed_level_analysis.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
summary=[]
for scenario in SCENARIOS:
    for method in METHODS:
        rr=[v for v in data if v["scenario"]==scenario and v["method"]==method]
        summary.append({"scenario":scenario,"method":method,"seeds":len(rr),
                        "mean_error_stop":float(np.mean([x["theta_error_at_stop"] for x in rr])),
                        "mean_error_final":float(np.mean([x["theta_error_final"] for x in rr])),
                        "exposed_at_stop":sum(x["exposed_at_stop"] for x in rr),
                        "corrected_after_attack":sum(x["corrected_after_attack"] for x in rr),
                        "attained20":sum(x["attained20"] for x in rr),
                        "mean_accepted_post":float(np.mean([x["post_accepted"] for x in rr])),
                        "mean_rejected_post":float(np.mean([x["post_rejected"] for x in rr])),
                        "seeds_with_error_increases":sum(x["post_nondecrease_steps"]>0 for x in rr),
                        "sampled_safety_violations":sum(x["sampled_safety_violations"] for x in rr)})
with (DST/"summary_analysis.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
report={"main_unchanged":True,"source_run":39538932151,"base_attack_steps":[15,43],
        "method_names":METHODS,"scenarios":list(SCENARIOS),"seeds_each":20,
        "native_episodes":len(audit),"native_samples":sum(x["samples"] for x in audit),
        "main_baseline_compared_fields":len(deviations),"max_baseline_difference":maxdiff,
        "full_parameter_vectors":True,"federated_parameter_dimension":4,
        "not_neural_network_backbone":True,
        "shadow":"Offline counterfactual using SAME observed actual plant path and clean synthetic reports",
        "shadow_never_fed_back":True,
        "not_independent_clean_physical_plant":True,
        "epsilon":EPS,"consecutive_hold_samples":HOLD,
        "post_observation_samples":STEPS-POST_START,
        "results":summary}
(DST/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")

def pretty(x):
    return f"{float(x):.3g}"

lines=[
    r"\subsection{Extended Native Post-Poisoning Deployment Audit}",
    r"\label{subsec:native-postpoison}",
    ("A separate IEEE 39-bus diagnostic experiment records the actual "
     "four-dimensional deployed controller coefficients and an offline "
     "same-operator clean-report shadow on the identical observed plant path. "
     "Knowledge-only and joint corruption are each tested with 20 seeds for "
     "FedRL, AEFC-no-TGOPA and AEFC-Full. The original attack window remains "
     "samples 15--43, while each native episode is extended to 220 samples, "
     "including 176 post-attack samples. These four coefficients are not "
     "a trained neural-network backbone; the shadow does not represent an "
     "independently simulated clean plant or a certified fixed optimum."),
    r"\begin{table*}[t]",
    r"\centering",
    r"\caption{Original native four-coefficient deployment under post-poisoning observation, 20 seeds per cell. An episode is corrected only if initially outside $\varepsilon=10^{-3}$ after attack and later remains inside for 20 consecutive samples. All counts use seeds, not time samples.}",
    r"\label{tab:native-postpoison}",
    r"\scriptsize",
    r"\begin{tabular}{@{}llcccccc@{}}",
    r"\toprule",
    r"Scenario & Method & Exposed & Corrected & Error at stop & Error at end & Accepted after & Error increased\\",
    r"\midrule"
]
for a in summary:
    label="Knowledge" if a["scenario"]=="knowledge" else "Joint"
    fields=[label,a["method"],str(a["exposed_at_stop"])+"/20",
            str(a["corrected_after_attack"])+"/20",
            pretty(a["mean_error_stop"]),pretty(a["mean_error_final"]),
            pretty(a["mean_accepted_post"]),str(a["seeds_with_error_increases"])+"/20"]
    lines.append(" & ".join(fields)+r"\\")
lines.extend([
    r"\bottomrule",
    r"\end{tabular}",
    r"\end{table*}",
    ("The reported error is the Euclidean distance to the dynamically updated "
     "offline clean-report shadow, rather than the G3 theorem's fixed certified "
     "target. The 120 per-seed trajectories pass an independent recomputation "
     "of deployment-vector norms and comparison of original-window fields "
     "against the unchanged Main Experiment (maximum difference "
     +pretty(maxdiff)+"). "
     "Neither a decrease in average error nor an observed correction implies "
     "a uniform contraction inequality or bounded cumulative deployment drift. "
     "The original native implementation still uses synthetic attack-provenance "
     "information, so this experiment does not validate an unprivileged online "
     "federation or the continuous-time robust CBF contract.")
])
(DST/"Results-Native-PostPoison.tex").write_text("\n\n".join(lines)+"\n")

print(json.dumps(report,ensure_ascii=False,indent=2))
