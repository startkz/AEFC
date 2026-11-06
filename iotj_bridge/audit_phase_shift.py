#!/usr/bin/env python3
"""Cross-run, seed-paired audit for a round-51 honest demand-change test.

This study differs from H3's within-episode step-12 change: its first 50
federation rounds are clean and the plant shifts from round 51 onward.
Both branches keep the identical 6-dimensional observation adapter.
"""
from __future__ import annotations
import argparse,csv,json,hashlib
from pathlib import Path
import numpy as np

def ci(x,seed=20261104):
    a=np.asarray(x,dtype=float)
    if len(a)==0:return None
    mu=float(a.mean())
    if len(a)<2:return [mu,None,None]
    rng=np.random.default_rng(seed)
    draws=rng.choice(a,size=(12000,len(a)),replace=True).mean(axis=1)
    q=np.quantile(draws,[.025,.975])
    return [mu,float(q[0]),float(q[1])]

def write(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for z in rows for k in z))
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def read(root):
    got={};errors=[]
    for p in sorted(Path(root).rglob("*.json")):
        if p.name.endswith(".manifest.json") or p.name in ("audit.json","summary.json"):continue
        try:
            d=json.loads(p.read_text(encoding="utf-8"));s=d["summary"]
            if s["case"]!=39 or s["clients"]!=5 or s["train_episodes"]!=1000 or s["completed_rounds"]!=200 or s["eval_episodes"]!=10:
                raise ValueError("not full predefined IEEE39 1000/200/10 trial")
            if s["attack"]!="clean" or s["shift_lambda"]!=1. or not s["fixed_traffic"]:
                raise ValueError("attack/parameter mismatch")
            if s["hetero"]=="shift":
                variant="phased"
                if s["shift_onset_round_0based"]!=50:raise ValueError("shift onset must be round 51")
            elif s["hetero"]=="base":
                variant="no_shift"
                if s["shift_onset_round_0based"] is not None:raise ValueError("no-shift requires no onset")
            else:raise ValueError("observation dimensions differ from baseline")
            seed=int(s["seed"]);key=(variant,seed)
            if key in got:raise ValueError("duplicate seed")
            if len(d["rounds"])!=200 or len(d["train_episodes"])!=1000 or len(d["tests"])!=10:
                raise ValueError("incomplete records")
            if sum(int(r["uplink_bytes"]) for r in d["rounds"])!=s["uplink_bytes"]:
                raise ValueError("application-layer byte mismatch")
            if any(len(r.get("per_client",[]))!=5 for r in d["rounds"]):
                raise ValueError("per-client telemetry incomplete")
            if any(len(t.get("client_outcomes",[]))!=5 for t in d["tests"]):
                raise ValueError("held-out per-client outcomes incomplete")
            if any(bool(r["shift_active"])!=(variant=="phased" and int(r["round"])>=50) for r in d["rounds"]):
                raise ValueError("federated shift phase mismatch")
            if any(bool(e["shift_active"])!=(variant=="phased" and e["episode"]>250) for e in d["train_episodes"]):
                raise ValueError("episode shift phase mismatch")
            for ep in d["train_episodes"]:
                for c in ep["client_outcomes"]:
                    affected=int(c["client_id"]) in (1,3)
                    demand=float(c["final_demand_ratio"])
                    if not (0.85<=demand<=1.2):
                        raise ValueError("implausible per-client demand ratio")
            mf=p.with_suffix(".manifest.json");ck=p.with_suffix(".pt")
            if not mf.is_file() or not ck.is_file():raise ValueError("missing checkpoint/manifest")
            m=json.loads(mf.read_text(encoding="utf-8"))
            if hashlib.sha256(ck.read_bytes()).hexdigest()!=m["checkpoint_sha256"]:
                raise ValueError("bad checkpoint SHA256")
            if hashlib.sha256(p.read_bytes()).hexdigest()!=m["source_json_sha256"]:
                raise ValueError("bad JSON SHA256")
            got[key]=(p,d)
        except Exception as e:errors.append({"file":str(p),"reason":str(e)})
    return got,errors

def metric_window(d,start,end,client,metric):
    return float(np.mean([float(r["per_client"][client][metric])
            for r in d["rounds"][start:end]]))

def demand_window(d,start,end,client):
    return float(np.mean([float(e["client_outcomes"][client]["final_demand_ratio"])
            for e in d["train_episodes"][start:end]]))

def audit(root,out):
    got,errors=read(root)
    seeds=sorted(set(s for v,s in got if v=="phased")&set(s for v,s in got if v=="no_shift"))
    if seeds!=list(range(80,90)):
        errors.append({"reason":f"expected ten exact matched seeds 80--89, got {seeds}"})
    trajectories=[];paired=[];means=[]
    for seed in seeds:
        phase=got[("phased",seed)][1];ctrl=got[("no_shift",seed)][1]
        for client in range(5):
            pc=phase["rounds"];bc=ctrl["rounds"]
            for k in range(200):
                a=pc[k]["per_client"][client];b=bc[k]["per_client"][client]
                trajectories.append({"seed":seed,"client_id":client,"affected":int(client in (1,3)),
                    "round":k+1,"shift_active":int(k>=50),
                    "weight_phased":a["aggregation_weight"],
                    "weight_no_shift":b["aggregation_weight"],
                    "weight_difference":float(a["aggregation_weight"])-float(b["aggregation_weight"]),
                    "drift_phased":a["prototype_drift"],"drift_no_shift":b["prototype_drift"],
                    "drift_difference":float(a["prototype_drift"])-float(b["prototype_drift"])})
            row={"seed":seed,"client_id":client,"affected":int(client in (1,3))}
            for name,metric in (("weight","aggregation_weight"),("drift","prototype_drift"),
                                ("score","credibility_score")):
                for condition,d in (("phased",phase),("no_shift",ctrl)):
                    pre=metric_window(d,40,50,client,metric)
                    post=metric_window(d,50,60,client,metric)
                    row[f"{name}_{condition}_pre41_50"]=pre
                    row[f"{name}_{condition}_post51_60"]=post
                    row[f"{name}_{condition}_change"]=post-pre
                row[f"{name}_difference_in_differences"]=row[f"{name}_phased_change"]-row[f"{name}_no_shift_change"]
            for condition,d in (("phased",phase),("no_shift",ctrl)):
                row[f"demand_{condition}_pre"]=demand_window(d,200,250,client)
                row[f"demand_{condition}_post"]=demand_window(d,250,300,client)
                evals=[t["client_outcomes"][client] for t in d["tests"]]
                row[f"eval_final_service_{condition}"]=float(np.mean([t["final_served_fraction"] for t in evals]))
                row[f"eval_mean_service_{condition}"]=float(np.mean([t["mean_served_fraction"] for t in evals]))
            if abs(row["demand_no_shift_post"]-row["demand_no_shift_pre"])>.015:
                errors.append({"seed":seed,"client":client,"reason":"nonshift demand changed abruptly"})
            if client in (1,3):
                delta=row["demand_phased_post"]-row["demand_phased_pre"]
                if not (.045<=delta<=.075):
                    errors.append({"seed":seed,"client":client,"reason":f"expected 6% phase demand jump; measured {delta}"})
            else:
                if abs(row["demand_phased_post"]-row["demand_phased_pre"])>.015:
                    errors.append({"seed":seed,"client":client,"reason":"unaffected demand changed"})
            paired.append(row)
        means.append({"seed":seed,"load_phase":phase["summary"]["mean_test_load_pct"],
                      "load_control":ctrl["summary"]["mean_test_load_pct"],
                      "load_delta":phase["summary"]["mean_test_load_pct"]-ctrl["summary"]["mean_test_load_pct"],
                      "safe_phase":phase["summary"]["safe_dwell_successes"]/10,
                      "safe_control":ctrl["summary"]["safe_dwell_successes"]/10,
                      "safe_delta":(phase["summary"]["safe_dwell_successes"]-ctrl["summary"]["safe_dwell_successes"])/10})
    summary=[]
    for client in range(5):
        arr=[r for r in paired if r["client_id"]==client]
        for metric in ("weight_difference_in_differences","drift_difference_in_differences",
                       "score_difference_in_differences",
                       "eval_mean_service_phased","eval_mean_service_no_shift"):
            result=ci([x[metric] for x in arr],seed=20261104+client)
            summary.append({"client_id":client,"affected":int(client in (1,3)),
                "metric":metric,"n_training_seeds":len(arr),
                "mean":result[0],"bootstrap95_low":result[1],"bootstrap95_high":result[2]})
    for metric in ("load_delta","safe_delta"):
        result=ci([x[metric] for x in means])
        summary.append({"client_id":"all","affected":"mixed","metric":metric,
                        "n_training_seeds":len(means),
                        "mean":result[0],"bootstrap95_low":result[1],"bootstrap95_high":result[2]})
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    write(out/"phased_per_client_round.csv",trajectories)
    write(out/"phased_per_client_paired.csv",paired)
    write(out/"phased_per_seed_system.csv",means)
    write(out/"Table_Phased_Client_DifferenceInDifferences.csv",summary)
    report={"purpose":"same-dimension phased honest demand shift (round 51)",
            "independent_unit":"training seed","n_matched_training_seeds":len(seeds),
            "onset_round_1based":51,"paired_window_pre":"rounds 41-50",
            "paired_window_post":"rounds 51-60",
            "errors":errors,"valid":not errors}
    (out/"phased_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    if trajectories:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,1,figsize=(10,7.2),sharex=True)
        for client in range(5):
            subset=[z for z in trajectories if z["client_id"]==client]
            for ax,metric in ((axes[0],"drift_difference"),(axes[1],"weight_difference")):
                vals=np.asarray([[z[metric] for z in subset if z["seed"]==seed]
                    for seed in seeds],float)
                avg=vals.mean(axis=0);std=vals.std(axis=0,ddof=1)/np.sqrt(len(seeds))
                xx=np.arange(1,201)
                label=f"Client {client}"+(" (shift)" if client in (1,3) else "")
                ax.plot(xx,avg,label=label)
                ax.fill_between(xx,avg-1.96*std,avg+1.96*std,alpha=.11)
        axes[0].set_ylabel("Drift: phased minus no-shift")
        axes[1].set_ylabel("Weight: phased minus no-shift")
        axes[1].set_xlabel("Federation round")
        for ax in axes:ax.axvline(51,ls="--",color="gray",alpha=.8);ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
        fig.tight_layout();fig.savefig(out/"Fig_Phased_Honest_Shift.png",dpi=300,bbox_inches="tight");plt.close(fig)
    if errors:raise SystemExit(2)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(audit(a.input,a.out),ensure_ascii=False))
