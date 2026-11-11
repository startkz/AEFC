#!/usr/bin/env python3
"""Fail-closed, matched-seed equal-byte audit for IoT-J R4 coordinate ablation.

No paper result or bilingual numerical reply is emitted if even one raw JSON,
model checkpoint, serialized-byte contract, episode, seed, or score is missing.
Independent unit is the whole training seed; no episode-as-seed pseudoreplication.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np

MODES=("adv","ordinary","coord_random","coord_gradtopk")
SEEDS=tuple(range(80,90))
EXPECTED={(s,m) for s in SEEDS for m in MODES}
REQUIRED_RULE={
    "coord_random":"uniform_random_coordinate_without_replacement",
    "coord_gradtopk":"sum_abs_raw_pre_adam_gradients",
}
def ensure(v,msg):
    if not v:raise ValueError(msg)
def near(a,b,msg,atol=1e-7):
    a=float(a);b=float(b)
    ensure(math.isfinite(a) and math.isfinite(b) and
           abs(a-b)<=atol*max(1.,abs(a),abs(b)),f"{msg}: {a} != {b}")
def hash_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()
def as_csv(path,rows):
    ensure(rows,"Empty output "+str(path))
    keys=sorted(set().union(*(x.keys() for x in rows)))
    with path.open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
        writer.writerows(rows)
def recovery(trace):
    streak=0
    for z in trace:
        valid=bool(z["safe"]) and bool(z["ac_converged"]) and float(z["restored_pct"])>=90.
        streak=streak+1 if valid else 0
        if streak>=5:return int(z["t"])-4
    return -1
def audit_file(path):
    d=json.loads(path.read_text(encoding="utf8"))
    s=d["summary"];seed=int(s["seed"]);mode=s["method"];key=(seed,mode)
    ensure(key in EXPECTED,"unexpected seed/method: "+str(key))
    required={
      "case":39,"clients":5,"train_episodes":1000,"train_episode_records":1000,
      "scheduled_rounds":200,"completed_rounds":200,"eval_episodes":10,
      "steps_per_episode":30,"fed_sync_interval":5,"batch_size":256,
      "hidden_size":128,"latent_size":32,"local_fit_steps":5,
      "sharing_steps":2,"fixed_traffic":1,"record_training_trace":1,
      "malicious_clients":0,
    }
    for k,v in required.items():
        ensure(int(s[k])==v,f"{key} wrong {k}={s[k]} expected {v}")
    ensure(s["backend"]=="pandapower AC quasi-static" and
           s["hetero"]=="dim" and s["attack"]=="clean" and s["weight_cap"]=="None",
           f"{key}: protocol mismatch")
    near(s["kappa"],.2,f"{key}: kappa",1e-12)
    if mode in REQUIRED_RULE:
        ensure(s["coordinate_selection_rule"]==REQUIRED_RULE[mode],
               f"{key}: coordinate rule mismatch")
    manifest=path.with_suffix(".manifest.json")
    ckpt=path.with_suffix(".pt")
    ensure(manifest.is_file() and ckpt.is_file(),f"{key}: missing JSON provenance or checkpoint")
    meta=json.loads(manifest.read_text())
    ensure(hash_file(path)==meta["source_json_sha256"],f"{key}: source JSON checksum mismatch")
    ensure(hash_file(ckpt)==meta["checkpoint_sha256"],f"{key}: checkpoint SHA mismatch")
    ensure(int(meta["training_episodes_executed"])==1000,f"{key}: incomplete budget")
    ensure(meta["git_commit"]==s.get("git_commit",meta["git_commit"]),
           f"{key}: hash metadata disagreement")
    ensure(len(d["rounds"])==200 and len(d["train_episodes"])==1000 and
           len(d["tests"])==10,f"{key}: invalid trace lengths")
    eprows=[]; selected_fractions=[]; round_bytes=[]
    for i,r in enumerate(d["rounds"]):
        ensure(int(r["round"])==i,f"{key}: bad federation round index")
        ensure(len(r["actual_serialized_client_bytes"])==5,f"{key}: missing client bytes")
        ensure(len(r["coordinate_selection"])==5,f"{key}: missing selector telemetry")
        total=sum(int(x) for x in r["actual_serialized_client_bytes"])
        ensure(total==int(r["uplink_bytes"]),f"{key}: per-client wire size mismatch")
        ensure(r["accepted"]==sum(int(c["accepted"]) for c in r["per_client"]),
               f"{key}: server accepted inconsistency")
        if mode in REQUIRED_RULE:
            for pos,v in enumerate(r["coordinate_selection"]):
                if v is None:
                    continue # permitted when no positive advantage exists
                ensure(v["rule"]==REQUIRED_RULE[mode],f"{key}: wrong selector rule")
                ensure(v["same_raw_loss_and_adam_steps"],f"{key}: altered optimizer objective")
                k=int(math.ceil(.2*int(v["dimension"])))
                ensure(int(v["k"])==k,f"{key}: k not matched")
                ensure(0<=int(v["overlap_final_delta_topk"])<=k,
                       f"{key}: invalid support overlap")
                ensure(float(v["selected_delta_l2"])<=float(v["global_delta_l2"])+1e-7,
                       f"{key}: invalid selected displacement norm")
                ensure(len(v["support_sha256"])==64 and len(v["final_adam_delta_sha256"])==64,
                       f"{key}: invalid selector provenance digest")
                if mode=="coord_gradtopk":
                    ensure(len(v["raw_gradient_score_sha256"])==64,
                           f"{key}: missing gradient scores SHA256")
                selected_fractions.append(float(v["overlap_final_delta_topk"])/k)
        round_bytes.append(total)
    ensure(sum(round_bytes)==int(s["uplink_bytes"]),f"{key}: sum upload mismatch")
    for i,t in enumerate(d["train_episodes"],start=1):
        ensure(int(t["episode"])==i,f"{key}: missing episode {i}")
        trace=t["trace"]
        ensure(1<=len(trace)<=30 and len(trace)==t["steps_executed"],f"{key}: missing step trace {i}")
        ensure([int(z["t"]) for z in trace]==list(range(1,len(trace)+1)),
               f"{key}: missing physical step {i}")
        actual=recovery(trace)
        ensure(int(t["recovery_step"])==actual,f"{key}: erroneous physical recovery step {i}")
        ensure(int(t["censored"])==int(actual<0),f"{key}: wrong censoring {i}")
        ensure(int(t["safe_dwell5"])==int(actual>=0),f"{key}: wrong dwell {i}")
        near(t["recovery_accuracy_pct"],trace[-1]["restored_pct"],
             f"{key}: actual terminal load ep{i}")
        near(t["average_restored_pct"],np.mean([z["restored_pct"] for z in trace]),
             f"{key}: area load ep{i}")
        eprows.append({"seed":seed,"mode":mode,"episode":i,
            "first_safe_dwell_start_step":actual,"censored":int(actual<0),
            "restricted_recovery_score":actual if actual>=0 else 31,
            "terminal_restored_load_pct":float(t["recovery_accuracy_pct"]),
            "restored_load_auc_pct":float(t["average_restored_pct"]),
            "steps_executed":len(trace),"safe_dwell":int(actual>=0)})
    ensure(sum(int(t["safe_dwell5"]) for t in d["tests"])==s["safe_dwell_successes"],
           f"{key}: evaluation success count mismatch")
    near(np.mean([t["final_restored_pct"] for t in d["tests"]]),
         s["mean_test_load_pct"],f"{key}: heldout load")
    return key,{
      "seed":seed,"mode":mode,"method":mode,"code_sha":meta["git_commit"],
      "model_checkpoint_sha256":meta["checkpoint_sha256"],
      "run_json_sha256":meta["source_json_sha256"],
      "application_uplink_bytes":int(s["uplink_bytes"]),
      "mean_final_load_pct":float(np.mean([v["terminal_restored_load_pct"] for v in eprows])),
      "last100_load_pct":float(np.mean([v["terminal_restored_load_pct"] for v in eprows[-100:]])),
      "mean_load_auc_pct":float(np.mean([v["restored_load_auc_pct"] for v in eprows])),
      "safe_dwell_fraction":float(np.mean([v["safe_dwell"] for v in eprows])),
      "last100_safe_dwell_fraction":float(np.mean([v["safe_dwell"] for v in eprows[-100:]])),
      "mean_restricted_recovery_score":float(np.mean([v["restricted_recovery_score"] for v in eprows])),
      "censored_count":sum(int(v["censored"]) for v in eprows),
      "selected_support_overlap_delta_topk_mean":
         float(np.mean(selected_fractions)) if selected_fractions else None,
      "heldout_load_pct":float(s["mean_test_load_pct"]),
      "heldout_safe_dwell_fraction":float(s["safe_dwell_successes"])/10.,
    },eprows,round_bytes
def seed_ci(values,rs):
    x=np.asarray(values,dtype=float)
    ensure(len(x)==len(SEEDS),"not 10 seed observations")
    rng=np.random.default_rng(rs)
    avg=x[rng.integers(0,len(x),size=(10000,len(x)))].mean(1)
    return float(np.mean(x)),float(np.quantile(avg,.025)),float(np.quantile(avg,.975))
def audit(root,out):
    root=Path(root);out=Path(out)
    rec={};episodes=[];bytes_by_seed={};errors=[]
    files=sorted(p for p in root.rglob("*.json")
                 if not p.name.endswith(".manifest.json") and p.name.endswith(".json"))
    for p in files:
        try:
            key,summary,eps,per_round_bytes=audit_file(p)
            ensure(key not in rec,f"Duplicate trial {key}")
            rec[key]=summary
            episodes.extend(eps)
            bytes_by_seed[key]=per_round_bytes
        except Exception as e:
            errors.append({"file":str(p),"reason":str(e)})
    missing=sorted(EXPECTED-set(rec))
    sha=sorted({r["code_sha"] for r in rec.values()})
    for seed in SEEDS:
        if all((seed,mode) in rec for mode in MODES):
            totals=[rec[(seed,mode)]["application_uplink_bytes"] for mode in MODES]
            if len(set(totals))!=1:
                errors.append({"seed":seed,"reason":"Actual serialized uplink bytes unequal",
                               "totals":dict(zip(MODES,totals))})
            for r in range(200):
                per_method={m:bytes_by_seed[(seed,m)][r] for m in MODES}
                if len(set(per_method.values()))!=1:
                    errors.append({"seed":seed,"round":r,"reason":"Roundwise byte mismatch",
                                   "per_method":per_method})
                    break
    if len(sha)!=1:errors.append({"reason":"Mismatched training source revisions","sha":sha})
    report={"passed":not errors and not missing and len(rec)==len(EXPECTED),
            "expected_runs":len(EXPECTED),"audited_runs":len(rec),
            "training_seeds":list(SEEDS),"methods":list(MODES),"missing":missing,
            "errors":errors,"git_source_shas":sha,
            "episodes_per_run":1000,"federation_rounds_per_run":200,
            "heldout_episodes_per_run":10,
            "aggregate_training_episode_rows":len(episodes),
            "independent_statistical_unit":"training seed",
            "platform":"IEEE39 quasi-static AC; not original Simulink--Python Fig5/6",
            "position":"Controls change support selected from same Adam displacement",
            "loss_and_optimizer":"AEFC/coordinate methods use matched positive-advantage loss and Adam steps",
            "not_claimed":"uniform Q-advantage error bound, guaranteed global improvement, dynamic physical safety"}
    out.mkdir(parents=True,exist_ok=True)
    (out/"r4_audit_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    if not report["passed"]:
        raise ValueError("R4 fail-closed matrix audit "+str(out/"r4_audit_report.json"))
    per_seed=[rec[k] for k in sorted(rec)]
    as_csv(out/"r4_per_seed.csv",per_seed)
    as_csv(out/"r4_per_episode.csv",episodes)
    metrics=("mean_final_load_pct","last100_load_pct","mean_load_auc_pct",
             "safe_dwell_fraction","last100_safe_dwell_fraction",
             "mean_restricted_recovery_score","censored_count",
             "heldout_load_pct","heldout_safe_dwell_fraction")
    summaries=[];paired=[]
    for mi,mode in enumerate(MODES):
        v=[rec[(seed,mode)] for seed in SEEDS]
        d={"mode":mode,"n_independent_seeds":len(v),
           "actual_application_bytes_per_run":v[0]["application_uplink_bytes"]}
        for k in metrics:
            a,b,c=seed_ci([x[k] for x in v],20261111+mi*100+len(k))
            d.update({k+"_mean":a,k+"_ci95_low":b,k+"_ci95_high":c})
        summaries.append(d)
        if mode=="adv":continue
        for k in metrics:
            values=[rec[(seed,"adv")][k]-rec[(seed,mode)][k] for seed in SEEDS]
            m,lo,hi=seed_ci(values,20261111+mi*157+len(k))
            paired.append({"comparison":"adv-minus-"+mode,"metric":k,
                           "paired_n_seeds":len(SEEDS),"mean_difference":m,
                           "bootstrap95_low":lo,"bootstrap95_high":hi})
    as_csv(out/"r4_summary.csv",summaries)
    as_csv(out/"r4_paired_seed_intervals.csv",paired)
    row_summary={r["mode"]:r for r in summaries}
    lines=[
      "# R4 observed IEEE39 AC equal-byte coordinate-ablation results",
      "",
      "> Strictly bounded evidence: 5-client quasi-static AC, not native Simulink.",
      "> Ten independent paired seeds; sample episodes and physical steps are not independent replicates.",
      "",
      "| Method | Mean final load (%) | Safe dwell (%) | Restricted score (failures=31) | Uplink bytes |",
      "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        v=row_summary[mode]
        lines.append("| {} | {:.3f} | {:.2f} | {:.3f} | {:,} |".format(
            mode,v["mean_final_load_pct_mean"],100*v["safe_dwell_fraction_mean"],
            v["mean_restricted_recovery_score_mean"],
            v["actual_application_bytes_per_run"]))
    lines.extend([
       "",
       "## Interpretation and limitations",
       "All reported numbers are calculated from SHA256-verified per-run JSON and actual transmitted application bytes.",
       "Random-coordinate and raw-gradient Top-k select k support locations but transmit values from the **same final Adam displacement**.",
       "The original delta-magnitude Top-k and the ordinary-loss Top-k are separate controls.",
       "Censored episodes are **not** treated as 0-step successes; the 31-step restricted score is **not** physical recovery time.",
       "Numerical direction does not imply guaranteed advantage sign, global improvement or Byzantine robustness.",
       "Results may be compared only in the IEEE39 quasi-static AC setting; they are not evidence for the original six-method native figures.",
       "",
       "## Paired training-seed uncertainty",
       "",
       "| Contrast | Metric | Mean difference | 95% bootstrap CI |",
       "|---|---|---:|---:|"
    ])
    for row in paired:
        if row["metric"] not in ("mean_final_load_pct","safe_dwell_fraction",
                                 "mean_restricted_recovery_score","heldout_load_pct"):continue
        lines.append("| {} | {} | {:+.5f} | [{:+.5f}, {:+.5f}] |".format(
            row["comparison"],row["metric"],row["mean_difference"],
            row["bootstrap95_low"],row["bootstrap95_high"]))
    (out/"r4_results_review_ready.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(audit(a.root,a.out),indent=2))
