#!/usr/bin/env python3
"""Recompute all four native no-oracle evaluation cells from raw MATLAB traces.

Refuses missing files, duplicate seeds, metric mismatches, or nonfinite values.
Does NOT claim G5 full-state certification.
"""
import csv, json, math, random
from pathlib import Path
import statistics

ROOT=Path("results/p0_nooracle_download")
OUT=Path("results/p0_native_unprivileged_verified")
OUT.mkdir(parents=True,exist_ok=True)
CELL_NAMES=("default","qmin-0p48","rho-0p09","trust-0p002")
METRICS=("integrated_squared_physical_deviation","integrated_absolute_physical_deviation",
         "integrated_postattack_physical_deviation","integrated_correction_effort",
         "max_same_operator_shadow_error","max_deployment_step_norm",
         "gate_reject_count","model_accept_count",
         "model_accepted_despite_gate_rejection_count")
TOL=1e-9
DT=1/60
STEPS=73
ATTACK_END=43
pairs={}
checks=0
all_rows=[]
max_diff=0.
errors=[]
for name in CELL_NAMES:
    basedir=ROOT/("AEFC-P0-no-oracle-"+name)
    folder=basedir/"AEFC-Full"
    summaries=sorted(folder.glob("seed_*.summary.json"))
    traces=sorted(folder.glob("seed_*.jsonl"))
    if len(summaries)!=20 or len(traces)!=20:
        errors.append(f"{name}: expected 20 summaries/traces, found {len(summaries)}/{len(traces)}")
        continue
    for seed in range(20):
        stem=f"seed_{seed:02d}"
        sj=json.loads((folder/(stem+".summary.json")).read_text())
        raw=[json.loads(s) for s in (folder/(stem+".jsonl")).read_text().splitlines() if s]
        if len(raw)!=STEPS:errors.append(f"{name} {stem}: unexpected samples {len(raw)}");continue
        if int(sj["seed"])!=seed or sj["method"]!="AEFC-Full" or any(int(t["seed"])!=seed for t in raw):
            errors.append(f"{name} {stem}: seed or method mismatch");continue
        values={}
        values["integrated_squared_physical_deviation"]=sum(sum(float(v)**2 for v in t["observation_normalized"]) for t in raw)*DT
        values["integrated_absolute_physical_deviation"]=sum(sum(abs(float(v)) for v in t["observation_normalized"]) for t in raw)*DT
        values["integrated_postattack_physical_deviation"]=sum(sum(float(v)**2 for v in t["observation_normalized"]) for t in raw[ATTACK_END:])*DT
        values["integrated_correction_effort"]=sum(sum((float(u)+float(a))**2 for u,a in zip(t["shield_action"],t["post_shield_attack"])) for t in raw)*DT
        values["max_same_operator_shadow_error"]=max(float(t["same_operator_shadow_error"]) for t in raw)
        values["max_deployment_step_norm"]=max(float(t["deployed_step_norm"]) for t in raw)
        values["gate_reject_count"]=sum(not bool(t["gate_decision"]) for t in raw)
        values["model_accept_count"]=sum(bool(t["adapt_accepted"]) for t in raw)
        values["model_accepted_despite_gate_rejection_count"]=sum(bool(t["adapt_accepted"]) and not bool(t["gate_decision"]) for t in raw)
        for key in METRICS:
            diff=abs(values[key]-float(sj[key]))
            checks+=1
            max_diff=max(max_diff,diff)
            if not math.isfinite(diff) or diff>TOL:
                errors.append(f"{name} {seed} {key} discrepancy {diff}")
        if float(sj["max_belief_distortion"])<0 or float(sj["max_same_operator_shadow_error"])<0:
            errors.append(f"{name} {seed}: invalid belief metrics")
        summary={"cell":name,"seed":seed}
        for k in METRICS:summary[k]=values[k]
        summary["min_native_margin"]=float(sj["min_native_margin"])
        summary["safety_violation"]=int(sj["safety_violation"])
        summary["recovery_time"]=float(sj["recovery_time"])
        summary["recovery_success"]=int(sj["recovery_success"])
        all_rows.append(summary)
        pairs[(name,seed)]=summary
if len(all_rows)!=80 or checks!=720:
    errors.append(f"expected 80 rows/720 comparisons, got {len(all_rows)}/{checks}")
def bootstrap(diffs,n=20000):
    rr=random.Random(20261021)
    means=[sum(diffs[rr.randrange(len(diffs))] for _ in diffs)/len(diffs) for _ in range(n)]
    means.sort()
    return [means[int(.025*n)],means[int(.975*n)]]
comparison={}
for name in CELL_NAMES[1:]:
    comparison[name]={}
    for key in ("integrated_squared_physical_deviation","integrated_postattack_physical_deviation",
                "integrated_correction_effort","max_same_operator_shadow_error",
                "model_accepted_despite_gate_rejection_count"):
        if all((name,seed) in pairs and ("default",seed) in pairs for seed in range(20)):
            d=[pairs[(name,s)][key]-pairs[("default",s)][key] for s in range(20)]
            comparison[name][key]={"paired_mean_delta":statistics.mean(d),
                                   "bootstrap95_each_comparison":bootstrap(d)}
table=[]
for name in CELL_NAMES:
    rr=[r for r in all_rows if r["cell"]==name]
    if not rr:continue
    table.append({"cell":name,"episodes":len(rr),"state_cost_mean":statistics.mean(r["integrated_squared_physical_deviation"] for r in rr),
                  "postattack_cost_mean":statistics.mean(r["integrated_postattack_physical_deviation"] for r in rr),
                  "correction_effort_mean":statistics.mean(r["integrated_correction_effort"] for r in rr),
                  "same_operator_belief_error_mean":statistics.mean(r["max_same_operator_shadow_error"] for r in rr),
                  "gate_rejections":sum(r["gate_reject_count"] for r in rr),
                  "model_accepts":sum(r["model_accept_count"] for r in rr),
                  "model_accepts_despite_gate_reject":sum(r["model_accepted_despite_gate_rejection_count"] for r in rr),
                  "physical_violations":sum(r["safety_violation"] for r in rr)})
audit={"source_run":39532719191,"backend":"native_matlab_R2024b_supplemental_no_oracle_decision",
       "original_Main_untouched":True,"independent_utility":True,
       "sample_count":len(all_rows)*STEPS,"episodes":len(all_rows),
       "raw_to_summary_metric_checks":checks,"max_numeric_discrepancy":max_diff,
       "comparison":comparison,"table":table,"errors":errors,
       "scope_warning":"Off-path shadow remains in same class. No independent full-state estimator nor continuous-time G5 certificate."}
(OUT/"audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
if all_rows:
    with (OUT/"summary.csv").open("w",newline="") as fo:
        w=csv.DictWriter(fo,fieldnames=list(all_rows[0]));w.writeheader();w.writerows(all_rows)
print(json.dumps({"table":table,"errors":errors,"checks":checks,"maxdiff":max_diff},ensure_ascii=False))
if errors:raise SystemExit(f"P0 no-oracle audit failure: {len(errors)} errors")
