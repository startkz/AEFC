#!/usr/bin/env python3
"""Strict audit of actual applied-aggregate-update physical effects.

Each comparison freezes the current encoder/head/critic and evaluates the
identical independently seeded AC demand scenario before and after the
server's true selected aggregate backbone update. Never tune using this
holdout. Empirical paired gains are not monotonicity or safety guarantees.
"""
import argparse,csv,hashlib,json,math
from pathlib import Path
from collections import defaultdict
import numpy as np

SEEDS=tuple(range(80,90))
ROUNDS=(50,100,200)
PROFILES=3
EXPECTED={(seed,round_id,profile) for seed in SEEDS for round_id in ROUNDS for profile in range(PROFILES)}
def must(condition,reason):
    if not condition:raise ValueError(reason)
def near(a,b,why,tol=1e-6):
    a,b=float(a),float(b)
    must(math.isfinite(a) and math.isfinite(b) and
         abs(a-b)<=tol*max(1.,abs(a),abs(b)),f"{why}: {a} != {b}")
def hash_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for x in iter(lambda:f.read(1024*1024),b""):h.update(x)
    return h.hexdigest()
def csv_save(p,rows):
    must(rows,"empty rows "+str(p))
    fields=sorted(set().union(*(r.keys() for r in rows)))
    with p.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def actual_safe_dwell(trace):
    n=0
    for z in trace:
        hit=bool(z["safe"]) and bool(z["ac_converged"]) and float(z["restored_pct"])>=90.
        n=n+1 if hit else 0
        if n>=5:return int(z["t"])-4
    return -1
def check_raw(p):
    d=json.loads(p.read_text());s=d["summary"];seed=int(s["seed"])
    must(seed in SEEDS and s["method"]=="adv","Unexpected seed/mode")
    required={"case":39,"clients":5,"train_episodes":1000,"completed_rounds":200,
              "eval_episodes":10,"batch_size":256,"hidden_size":128,"latent_size":32,
              "local_fit_steps":5,"sharing_steps":2,"fixed_traffic":1}
    for k,v in required.items():must(int(s[k])==v,f"Protocol {k}")
    must(s["hetero"]=="dim" and s["attack"]=="clean","unexpected physical environment")
    must(s["aggregate_diagnostic_rounds"]==list(ROUNDS) and
         s["aggregate_diagnostic_profiles"]==PROFILES,"wrong checkpoints")
    near(s["kappa"],.2,"sparse ratio",1e-12)
    m=p.with_suffix(".manifest.json");ck=p.with_suffix(".pt")
    must(m.exists() and ck.exists(),"missing source model/provenance")
    meta=json.loads(m.read_text())
    must(hash_file(p)==meta["source_json_sha256"],"JSON checksum")
    must(hash_file(ck)==meta["checkpoint_sha256"],"checkpoint checksum")
    must(int(meta["training_episodes_executed"])==1000,"missing training")
    must(len(d["rounds"])==200 and len(d["tests"])==10,"missing federated/eval rounds")
    must(sum(int(x["uplink_bytes"]) for x in d["rounds"])==s["uplink_bytes"],
         "uplink accounting mismatch")
    rows=[];known=set()
    for x in s["aggregate_candidate_update_impact"]:
        n=int(x["round"]);profile=int(x["scenario_seed"])-(300000+seed*1000+n*10)
        key=(seed,n,profile)
        must(key in EXPECTED and key not in known,"extra or duplicate counterfactual")
        known.add(key)
        must(x["no_training_feedback"] is True and
             x["same_frozen_local_adapters"] is True,"learning contamination")
        near(float(x["actual_applied_delta_l2"]),d["rounds"][n-1]["direction_norm"],
             "actual aggregate update norm",1e-5)
        for side in ("pre","post"):
            trace=x[side+"_physical_trace"]
            must(1<=len(trace)<=30,"missing physical step records")
            must([int(z["t"]) for z in trace]==list(range(1,len(trace)+1)),
                 "nonconsecutive physical time")
            rt=actual_safe_dwell(trace)
            must(rt==int(x[side+"_recovery_step"]),f"{side} first-safe window mismatch")
            must(int(x[side+"_censored"])==int(rt<0),f"{side} right-censored mismatch")
            must(int(x[side+"_safe_dwell5"])==int(rt>=0),f"{side} unsafe recovery flag")
            near(trace[-1]["restored_pct"],x[side+"_final_restored_pct"],side+" load")
            near(np.mean([z["restored_pct"] for z in trace]),
                 x[side+"_average_load_pct"],side+" load AUC")
        near(x["post_final_restored_pct"]-x["pre_final_restored_pct"],
             x["paired_final_load_gain_pp"],"wrong physical gain")
        near(x["post_average_load_pct"]-x["pre_average_load_pct"],
             x["paired_load_auc_gain_pp"],"wrong AUC gain")
        rows.append({
           "seed":seed,"checkpoint_round":n,"physical_profile":profile,
           "source_commit":meta["git_commit"],
           "checkpoint_sha256":meta["checkpoint_sha256"],
           "applied_delta_l2":x["actual_applied_delta_l2"],
           "paired_terminal_load_gain_pp":x["paired_final_load_gain_pp"],
           "paired_auc_gain_pp":x["paired_load_auc_gain_pp"],
           "paired_safe_dwell_change":int(x["post_safe_dwell5"])-int(x["pre_safe_dwell5"]),
           "pre_recovery_step":x["pre_recovery_step"],
           "post_recovery_step":x["post_recovery_step"],
           "pre_censored":x["pre_censored"],"post_censored":x["post_censored"],
        })
    must(len(known)==len(ROUNDS)*PROFILES,"missing frozen-state comparisons")
    return seed,meta["git_commit"],rows
def interval(v,seed):
    a=np.array(v,dtype=float)
    must(len(a)==10,"Require 10 independent seed summaries")
    rng=np.random.default_rng(seed)
    means=a[rng.integers(0,10,size=(10000,10))].mean(1)
    return float(np.mean(a)),float(np.quantile(means,.025)),float(np.quantile(means,.975))
def audit(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    records={};errors=[];sha=[]
    for p in sorted(root.rglob("*.json")):
        if p.name.endswith(".manifest.json"):continue
        try:
            seed,src,rows=check_raw(p)
            must(seed not in records,"Duplicate source seed "+str(seed))
            records[seed]=rows;sha.append(src)
        except Exception as e:errors.append({"file":str(p),"reason":str(e)})
    missing=sorted(set(SEEDS)-set(records))
    if len(set(sha))!=1:errors.append({"reason":"Source code SHA differs","shas":list(set(sha))})
    report={
      "passed":len(records)==10 and not missing and not errors,
      "expected_training_seeds":10,"audited_training_seeds":len(records),
      "expected_paired_physical_profiles":len(EXPECTED),
      "audited_paired_profiles":sum(len(x) for x in records.values()),
      "missing_seeds":missing,"errors":errors,"source_commits":sorted(set(sha)),
      "scope":"actual applied aggregate backbone update under same frozen local adapters; deterministic IEEE39 AC",
      "not_proven":"global training monotonicity, optimal policy advantage, dynamic frequency safety"}
    (out/"r4_aggregate_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    if not report["passed"]:raise ValueError("Fail closed: "+str(out/"r4_aggregate_audit.json"))
    rows=[r for k in sorted(records) for r in records[k]]
    csv_save(out/"r4_aggregate_per_scenario.csv",rows)
    per_seed=[]
    for seed in SEEDS:
        for checkpoint in ROUNDS:
            cohort=[x for x in records[seed] if x["checkpoint_round"]==checkpoint]
            must(len(cohort)==PROFILES,"Incomplete heldout scenario block")
            per_seed.append({
                "seed":seed,"checkpoint_round":checkpoint,
                "mean_terminal_load_gain_pp":float(np.mean([x["paired_terminal_load_gain_pp"] for x in cohort])),
                "mean_auc_gain_pp":float(np.mean([x["paired_auc_gain_pp"] for x in cohort])),
                "mean_safe_dwell_change":float(np.mean([x["paired_safe_dwell_change"] for x in cohort])),
                "mean_update_l2":float(np.mean([x["applied_delta_l2"] for x in cohort]))
            })
    csv_save(out/"r4_aggregate_per_seed_checkpoint.csv",per_seed)
    stats=[]
    for idx,checkpoint in enumerate(ROUNDS):
        cohort=[x for x in per_seed if x["checkpoint_round"]==checkpoint]
        for metric in ("mean_terminal_load_gain_pp","mean_auc_gain_pp",
                       "mean_safe_dwell_change","mean_update_l2"):
            mean,lo,hi=interval([x[metric] for x in cohort],20261111+idx*91+len(metric))
            stats.append({"round":checkpoint,"metric":metric,"independent_seeds":10,
                          "mean":mean,"bootstrap95_low":lo,"bootstrap95_high":hi})
    csv_save(out/"r4_aggregate_seed_summary.csv",stats)
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(audit(a.root,a.out),indent=2))
