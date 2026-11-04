#!/usr/bin/env python3
"""Independent audit and figures for temporal-credibility and per-client drift studies."""
from __future__ import annotations
import argparse,csv,json,hashlib,math
from collections import defaultdict
from pathlib import Path
import numpy as np

def write_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def mean_ci(values,seed=20261104,draws=10000):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)]
    if not len(x):return (None,None,None)
    m=float(x.mean())
    if len(x)==1:return (m,None,None)
    rng=np.random.default_rng(seed)
    boot=rng.choice(x,size=(draws,len(x)),replace=True).mean(axis=1)
    lo,hi=np.quantile(boot,[.025,.975])
    return m,float(lo),float(hi)

def load_runs(root):
    root=Path(root);files=sorted(p for p in root.rglob("*.json")
        if not p.name.endswith(".manifest.json") and
        p.name not in ("audit.json","summary.json","gate_report.json"))
    runs=[];errors=[]
    for p in files:
        try:
            d=json.loads(p.read_text(encoding="utf-8"));s=d["summary"]
            if not all(k in d for k in ("rounds","tests","train_episodes")):raise ValueError("missing run sections")
            if len(d["rounds"])!=s["completed_rounds"]:raise ValueError("round count mismatch")
            if len(d["tests"])!=s["eval_episodes"]:raise ValueError("test count mismatch")
            if len(d["train_episodes"])!=s["train_episodes"]:raise ValueError("train episode count mismatch")
            if sum(int(x["uplink_bytes"]) for x in d["rounds"])!=int(s["uplink_bytes"]):
                raise ValueError("application-byte sum mismatch")
            if [int(x["episode"]) for x in d["train_episodes"]]!=list(range(1,s["train_episodes"]+1)):
                raise ValueError("non-consecutive training episodes")
            for r in d["rounds"]:
                pc=r.get("per_client",[])
                if len(pc)!=int(s["clients"]):raise ValueError("per-client round telemetry missing")
                ids=[int(x["client_id"]) for x in pc]
                if ids!=list(range(int(s["clients"]))):raise ValueError("client ID ordering mismatch")
                accepted=[x for x in pc if x["accepted"]]
                if accepted and abs(sum(float(x["aggregation_weight"]) for x in accepted)-1.)>1.e-6:
                    raise ValueError("aggregation weights do not sum to one")
            manifest=p.with_suffix(".manifest.json");checkpoint=p.with_suffix(".pt")
            if manifest.exists():
                m=json.loads(manifest.read_text(encoding="utf-8"))
                if not checkpoint.exists():raise ValueError("checkpoint missing")
                if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=m["checkpoint_sha256"]:
                    raise ValueError("checkpoint SHA256 mismatch")
                if m.get("source_json_sha256") and hashlib.sha256(p.read_bytes()).hexdigest()!=m["source_json_sha256"]:
                    raise ValueError("JSON SHA256 mismatch")
                if int(m["training_episodes_executed"])!=int(s["train_episodes"]):
                    raise ValueError("manifest episode count mismatch")
            runs.append((p,d))
        except Exception as e:errors.append({"path":str(p),"reason":str(e)})
    return runs,errors

def timing_audit(root,out):
    runs,errors=load_runs(root);allowed={"clean","immediate_metadata","delayed_metadata",
        "immediate_credibility","temporal_credibility"}
    per_round=[];run_rows=[];detection=[]
    expected_onset={"clean":None,"immediate_metadata":1,"delayed_metadata":5,
                    "immediate_credibility":1,"temporal_credibility":50}
    for p,d in runs:
        s=d["summary"];condition=s["attack"]
        if condition not in allowed:continue
        if s["case"]!=39 or s["clients"]!=5 or s["train_episodes"]!=500 or s["completed_rounds"]!=100 or s["eval_episodes"]!=10:
            errors.append({"path":str(p),"reason":"unexpected timing-study design"})
            continue
        onset=expected_onset[condition]
        if int(s["attack_start_round_0based"])!=int(0 if onset is None else onset):
            errors.append({"path":str(p),"reason":"attack onset metadata mismatch"})
        bad=s.get("malicious_client_ids",[])
        if condition=="clean" and bad:errors.append({"path":str(p),"reason":"clean control has malicious IDs"})
        if condition!="clean" and bad!=[4]:errors.append({"path":str(p),"reason":"expected single malicious client 4"})
        weights=[];ratios=[]
        for r in d["rounds"]:
            rid=int(r["round"])
            active=(condition!="clean" and rid>=int(onset))
            if bool(r["attack_active"])!=active:
                errors.append({"path":str(p),"reason":f"attack phase boundary error at round {rid}"})
            pc=r["per_client"];mal=pc[4]
            if bool(mal["attack_active"])!=active:
                errors.append({"path":str(p),"reason":f"malicious client phase boundary error at round {rid}"})
            if condition in ("immediate_metadata","delayed_metadata") and active and mal["update_forgery"]:
                errors.append({"path":str(p),"reason":"metadata-only condition changed the update"})
            if condition in ("immediate_credibility","temporal_credibility") and active and not mal["update_forgery"]:
                errors.append({"path":str(p),"reason":"credibility condition failed to forge update"})
            w=float(mal["aggregation_weight"]);hon=float(np.mean([x["aggregation_weight"] for x in pc[:4]]))
            ratio=w/max(hon,1.e-12);weights.append(w);ratios.append(ratio)
            per_round.append({"condition":condition,"seed":s["seed"],"round":rid+1,
                "attack_active":int(active),"malicious_weight":w,
                "malicious_to_honest_mean_ratio":ratio,
                "malicious_drift":mal["prototype_drift"],
                "malicious_drift_penalty":mal["drift_penalty"],
                "malicious_score":mal["credibility_score"],
                "malicious_update_norm":mal["update_norm_clipped"],
                "global_direction_norm":r["direction_norm"],
                "uplink_bytes":r["uplink_bytes"]})
        start=int(onset or 0)
        detect=None
        if condition=="temporal_credibility":
            # This is a weight-suppression diagnostic, NOT an authenticated attack detector.
            for j in range(start,len(ratios)-2):
                if all(ratios[k]<=.25 for k in (j,j+1,j+2)):
                    detect=j;break
            pre_suppression=[j for j in range(0,max(0,start-2))
                             if all(ratios[k]<=.25 for k in (j,j+1,j+2))]
            post=np.asarray(weights[start:],float);post_ratio=np.asarray(ratios[start:],float)
            pre=np.asarray(weights[max(0,start-10):start],float)
            detection.append({"seed":s["seed"],"attack_onset_round":start+1,
                "sustained_weight_suppression":int(detect is not None),
                "suppression_start_round":None if detect is None else detect+1,
                "suppression_lag_rounds":None if detect is None else detect-start,
                "observed_suppression_pre_attack_windows":len(pre_suppression),
                "first_pre_attack_suppression_round":None if not pre_suppression else pre_suppression[0]+1,
                "postonset_exposure_episodes_until_confirmation":250 if detect is None else (detect-start+3)*5,
                "right_censored_postattack_rounds":50 if detect is None else 0,
                "pre_last10_mean_malicious_weight":float(pre.mean()),
                "post_first10_mean_malicious_weight":float(post[:10].mean()),
                "first10_weight_change_pp":float(100*(post[:10].mean()-pre.mean())),
                "mean_post_attack_malicious_weight":float(post.mean()),
                "mean_post_attack_weight_ratio":float(post_ratio.mean()),
                "first3_attack_round_mean_weight":float(post[:3].mean()),
                "post_attack_weight_mass":float(post.sum()),
                "mean_post_attack_global_direction_norm":float(np.mean([x["direction_norm"] for x in d["rounds"][start:]]))})
        run_rows.append({"condition":condition,"seed":s["seed"],
            "mean_malicious_weight":float(np.mean(weights)),
            "mean_attack_phase_weight":float(np.mean(weights[start:])) if condition!="clean" else None,
            "mean_malicious_to_honest_ratio":float(np.mean(ratios)),
            "mean_test_load_pct":s["mean_test_load_pct"],
            "safe_dwell_rate":s["safe_dwell_successes"]/s["test_count"],
            "uplink_bytes":s["uplink_bytes"]})
    if len(run_rows)!=50:
        errors.append({"path":str(root),"reason":f"expected 50 timing runs, found {len(run_rows)}"})
    # Summaries use training seeds, not rounds or test episodes, as the independent unit.
    summary=[]
    for condition in sorted({x["condition"] for x in run_rows}):
        z=[x for x in run_rows if x["condition"]==condition]
        for metric in ("mean_malicious_weight","mean_attack_phase_weight","mean_malicious_to_honest_ratio",
                       "mean_test_load_pct","safe_dwell_rate","uplink_bytes"):
            vals=[x[metric] for x in z if x[metric] is not None]
            m,lo,hi=mean_ci(vals,seed=20261104+len(summary))
            summary.append({"condition":condition,"metric":metric,"n_seeds":len(vals),
                            "mean":m,"bootstrap95_low":lo,"bootstrap95_high":hi})
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"timing_per_round.csv",per_round)
    write_csv(out/"timing_per_seed.csv",run_rows)
    write_csv(out/"temporal_detection_lag.csv",detection)
    write_csv(out/"timing_summary.csv",summary)
    report={"study":"IEEE39, N=5, M=1, 500 episodes, 100 federation rounds, 10 held-out episodes",
            "attack_modes":sorted(allowed),"expected_runs":50,"valid_runs":len(run_rows),
            "independent_unit":"training seed","weight_suppression_rule":
            "malicious weight / mean honest-client weight <= 0.25 for three consecutive rounds; not an attack detector",
            "exposure_window_episodes":"(suppression lag + 3 confirmation rounds) * 5 episodes; 250 episodes right-censored if not suppressed",
            "interpretation":"Report pre-attack suppression false positives and malicious weight mass, not detection accuracy or verified learning damage.",
            "errors":errors}
    (out/"timing_audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if per_round:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(1,2,figsize=(13,4.8),sharey=True)
        panels=[(("immediate_credibility","temporal_credibility"),"Utility + prototype + update forgery"),
                (("immediate_metadata","delayed_metadata"),"Utility + prototype forgery only")]
        for ax,(conditions,title) in zip(axs,panels):
            for cond in conditions:
                seeds=sorted({x["seed"] for x in per_round if x["condition"]==cond})
                mat=np.asarray([[next(x["malicious_weight"] for x in per_round
                    if x["condition"]==cond and x["seed"]==seed and x["round"]==r)
                    for r in range(1,101)] for seed in seeds],dtype=float)
                mu=mat.mean(axis=0);se=mat.std(axis=0,ddof=1)/math.sqrt(len(seeds))
                ax.plot(np.arange(1,101),mu,label=cond.replace("_"," "))
                ax.fill_between(np.arange(1,101),mu-1.96*se,mu+1.96*se,alpha=.15)
                onset=expected_onset[cond]+1
                ax.axvline(onset,linestyle="--",alpha=.55)
            ax.set_title(title);ax.set_xlabel("Federation round")
            ax.grid(alpha=.25);ax.legend(fontsize=8)
        axs[0].set_ylabel("Malicious client's aggregation weight")
        fig.tight_layout();fig.savefig(out/"Fig_Temporal_Credibility.png",dpi=300,bbox_inches="tight");plt.close(fig)
    if errors:raise SystemExit(2)
    return report

def per_client_audit(root,out):
    runs,errors=load_runs(root);client_rows=[];seed_rows=[];round_rows=[]
    variants={( "dim",1.0):"baseline"}
    for p,d in runs:
        s=d["summary"];het=s["hetero"];lam=round(float(s["shift_lambda"]),3)
        if s["case"]!=39 or s["clients"]!=5 or s["train_episodes"]!=1000 or s["completed_rounds"]!=200 or s["eval_episodes"]!=10:
            errors.append({"path":str(p),"reason":"unexpected per-client study design"});continue
        if het not in ("dim","shift") or (het=="shift" and lam not in (0.,.5,1.,2.)) or (het=="dim" and lam!=1.):
            errors.append({"path":str(p),"reason":"unexpected heterogeneity/lambda setting"});continue
        # Aggregate client telemetry across federation rounds for each run.
        metrics={i:[] for i in range(5)}
        for r in d["rounds"]:
            accepted=[m for m in r["per_client"] if m["accepted"]]
            no_drift_scores=[float(m["credibility_score"])/max(float(m["drift_penalty"]),1.e-12) for m in accepted]
            denom=float(sum(no_drift_scores))
            cf={int(m["client_id"]):(no_drift_scores[j]/denom if denom>0 else 1./len(accepted))
                for j,m in enumerate(accepted)}
            for m in r["per_client"]:
                i=int(m["client_id"])
                enriched={**m,"counterfactual_weight_lambda0":float(cf.get(i,0.))}
                metrics[i].append(enriched)
                round_rows.append({"hetero":het,"shift_lambda":lam,"seed":s["seed"],
                    "round":int(r["round"])+1,"client_id":i,
                    "prototype_drift":m["prototype_drift"],
                    "aggregation_weight":m["aggregation_weight"],
                    "counterfactual_weight_lambda0":float(cf.get(i,0.)),
                    "drift_induced_weight_change":float(m["aggregation_weight"])-float(cf.get(i,0.)),
                    "weight_ratio_to_equal":m["weight_ratio_to_equal"],
                    "drift_penalty":m["drift_penalty"],
                    "credibility_score":m["credibility_score"]})
        eval_by_client={i:[] for i in range(5)}
        for t in d["tests"]:
            if len(t.get("client_outcomes",[]))!=5:errors.append({"path":str(p),"reason":"test client outcomes missing"})
            for z in t.get("client_outcomes",[]):eval_by_client[int(z["client_id"])].append(z)
        train_by_client={i:[] for i in range(5)}
        for ep in d["train_episodes"]:
            outcomes=ep.get("client_outcomes",[])
            if len(outcomes)!=5:errors.append({"path":str(p),"reason":"training episode client outcomes missing"});continue
            for z in outcomes:train_by_client[int(z["client_id"])].append(z)
        train_demand_mean={}
        for i in range(5):
            vals=[float(z["final_demand_ratio"]) for z in train_by_client[i]]
            train_demand_mean[i]=float(np.mean(vals)) if vals else None
            expected=(1.06 if i in (1,3) else 1.0) if het=="shift" else 1.0
            if train_demand_mean[i] is None or abs(train_demand_mean[i]-expected)>.01:
                errors.append({"path":str(p),"reason":f"mean demand assignment mismatch seed {s['seed']} client {i}: observed {train_demand_mean[i]}, expected {expected}"})
        run_client=[]
        for i in range(5):
            mm=metrics[i];ee=eval_by_client[i]
            row={"hetero":het,"condition":"shift" if het=="shift" else "no_shift",
                 "shift_lambda":lam,"seed":s["seed"],"client_id":i,
                 "train_mean_final_demand_ratio":train_demand_mean[i],
                 "shift_affected":int(het=="shift" and i in (1,3)),
                 "mean_drift":float(np.mean([x["prototype_drift"] for x in mm])),
                 "mean_weight":float(np.mean([x["aggregation_weight"] for x in mm])),
                 "mean_counterfactual_weight_lambda0":float(np.mean([x["counterfactual_weight_lambda0"] for x in mm])),
                 "mean_drift_induced_weight_change":float(np.mean([x["aggregation_weight"]-x["counterfactual_weight_lambda0"] for x in mm])),
                 "mean_weight_ratio_to_equal":float(np.mean([x["weight_ratio_to_equal"] for x in mm])),
                 "mean_drift_penalty":float(np.mean([x["drift_penalty"] for x in mm])),
                 "mean_credibility_score":float(np.mean([x["credibility_score"] for x in mm])),
                 "eval_mean_served_fraction":float(np.mean([x["mean_served_fraction"] for x in ee])),
                 "eval_final_served_fraction":float(np.mean([x["final_served_fraction"] for x in ee])),
                 "eval_demand_ratio":float(np.mean([x["mean_demand_ratio"] for x in ee])),
                 "eval_final_demand_ratio":float(np.mean([x["final_demand_ratio"] for x in ee])),
                 "eval_first90_step_mean":float(np.mean([x["first_90pct_step"] for x in ee if x["first_90pct_step"]>0])) if any(x["first_90pct_step"]>0 for x in ee) else None}
            client_rows.append(row);run_client.append(row)
        shifted=[x for x in run_client if x["shift_affected"]]
        stable=[x for x in run_client if not x["shift_affected"]]
        client13=[x for x in run_client if x["client_id"] in (1,3)]
        client024=[x for x in run_client if x["client_id"] in (0,2,4)]
        seed_rows.append({"hetero":het,"shift_lambda":lam,"seed":s["seed"],
            "shifted_mean_drift":float(np.mean([x["mean_drift"] for x in shifted])) if shifted else None,
            "unshifted_mean_drift":float(np.mean([x["mean_drift"] for x in stable])),
            "shifted_mean_weight":float(np.mean([x["mean_weight"] for x in shifted])) if shifted else None,
            "unshifted_mean_weight":float(np.mean([x["mean_weight"] for x in stable])),
            "shifted_mean_served":float(np.mean([x["eval_mean_served_fraction"] for x in shifted])) if shifted else None,
            "unshifted_mean_served":float(np.mean([x["eval_mean_served_fraction"] for x in stable])),
            "client13_mean_drift":float(np.mean([x["mean_drift"] for x in client13])),
            "client024_mean_drift":float(np.mean([x["mean_drift"] for x in client024])),
            "client13_mean_weight":float(np.mean([x["mean_weight"] for x in client13])),
            "client024_mean_weight":float(np.mean([x["mean_weight"] for x in client024])),
            "client13_mean_counterfactual_weight_lambda0":float(np.mean([x["mean_counterfactual_weight_lambda0"] for x in client13])),
            "client024_mean_counterfactual_weight_lambda0":float(np.mean([x["mean_counterfactual_weight_lambda0"] for x in client024])),
            "client13_mean_drift_induced_weight_change":float(np.mean([x["mean_drift_induced_weight_change"] for x in client13])),
            "client024_mean_drift_induced_weight_change":float(np.mean([x["mean_drift_induced_weight_change"] for x in client024])),
            "client13_mean_served":float(np.mean([x["eval_mean_served_fraction"] for x in client13])),
            "client024_mean_served":float(np.mean([x["eval_mean_served_fraction"] for x in client024])),
            "client13_mean_final_demand_ratio":float(np.mean([train_demand_mean[i] for i in (1,3)])),
            "client024_mean_final_demand_ratio":float(np.mean([train_demand_mean[i] for i in (0,2,4)])),
            "mean_test_load_pct":float(s["mean_test_load_pct"]),
            "safe_dwell_rate":float(s["safe_dwell_successes"]/s["test_count"]),
            "uplink_bytes":int(s["uplink_bytes"])})

    if len(seed_rows)!=50:
        errors.append({"path":str(root),"reason":f"expected 50 per-client runs, found {len(seed_rows)}"})
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"per_client_by_seed.csv",client_rows)
    write_csv(out/"per_client_per_round.csv",round_rows)
    write_csv(out/"per_client_run_summary.csv",seed_rows)
    # Main table: 10 seeds per lambda, training seed is the independent unit.
    table=[]
    for lam in (0.,.5,1.,2.):
        z=[x for x in seed_rows if x["hetero"]=="shift" and x["shift_lambda"]==lam]
        if len(z)!=10:continue
        for metric in ("shifted_mean_drift","unshifted_mean_drift",
                       "shifted_mean_weight","unshifted_mean_weight",
                       "client13_mean_counterfactual_weight_lambda0","client024_mean_counterfactual_weight_lambda0",
                       "client13_mean_drift_induced_weight_change","client024_mean_drift_induced_weight_change",
                       "shifted_mean_served","unshifted_mean_served",
                       "mean_test_load_pct","safe_dwell_rate"):
            vals=[x[metric] for x in z if x[metric] is not None]
            m,lo,hi=mean_ci(vals,seed=20261105+int(lam*10)+len(table))
            table.append({"shift_lambda":lam,"metric":metric,"n_seeds":len(vals),
                          "mean":m,"bootstrap95_low":lo,"bootstrap95_high":hi})
    write_csv(out/"Table_PerClient_Drift_Lambda_Sensitivity.csv",table)
    # The historical hetero=dim controls have fewer observation coordinates on
    # odd clients than hetero=shift. Their contrast is NOT a shift-only causal test.
    # Do not emit the confounded paired difference table. The separate
    # audit_phase_shift.py uses hetero=base and hetero=shift with identical
    # adapter dimensions and a round-51 intervention.
    report={"study":"IEEE39, N=5 honest clients, 1000 episodes, 200 rounds, 10 held-out episodes",
            "shift":"6% legitimate load demand increase at local control step 12 in each episode for clients 1 and 3",
            "lambda_grid":[0.,.5,1.,2.],"historical_no_shift_diagnostic":"hetero=dim, lambda=1 (observation dimensions differ; no causal cross-scenario comparison)",
            "valid_causal_control":"Run audit_phase_shift.py on same-dimension base versus staged-shift pairs",
            "expected_runs":50,"valid_runs":len(seed_rows),
            "independent_unit":"training seed; client and round are repeated measurements",
            "errors":errors}
    (out/"per_client_audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if round_rows:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(2,1,figsize=(10,8),sharex=True)
        for client in range(5):
            mat=[]
            for seed in sorted({x["seed"] for x in round_rows if x["hetero"]=="shift" and x["shift_lambda"]==1.}):
                row=sorted([x for x in round_rows if x["hetero"]=="shift" and x["shift_lambda"]==1.
                            and x["seed"]==seed and x["client_id"]==client],key=lambda x:x["round"])
                mat.append([x["prototype_drift"] for x in row])
            mat=np.asarray(mat,float);mu=mat.mean(axis=0)
            se=mat.std(axis=0,ddof=1)/math.sqrt(len(mat))
            label=f"Client {client}"+(" (6% demand shift)" if client in (1,3) else "")
            axs[0].plot(np.arange(1,201),mu,label=label)
            axs[0].fill_between(np.arange(1,201),mu-1.96*se,mu+1.96*se,alpha=.12)
            matw=[]
            for seed in sorted({x["seed"] for x in round_rows if x["hetero"]=="shift" and x["shift_lambda"]==1.}):
                row=sorted([x for x in round_rows if x["hetero"]=="shift" and x["shift_lambda"]==1.
                            and x["seed"]==seed and x["client_id"]==client],key=lambda x:x["round"])
                matw.append([x["aggregation_weight"] for x in row])
            matw=np.asarray(matw,float);muw=matw.mean(axis=0)
            sew=matw.std(axis=0,ddof=1)/math.sqrt(len(matw))
            axs[1].plot(np.arange(1,201),muw,label=label)
            axs[1].fill_between(np.arange(1,201),muw-1.96*sew,muw+1.96*sew,alpha=.12)
        axs[0].set_ylabel("Prototype drift $d_i^t$")
        axs[1].set_ylabel("Aggregation weight $w_i^t$")
        axs[1].set_xlabel("Federation round")
        for ax in axs:ax.grid(alpha=.25);ax.legend(ncol=2,fontsize=8)
        fig.tight_layout();fig.savefig(out/"Fig_PerClient_Drift_Weight.png",dpi=300,bbox_inches="tight");plt.close(fig)
    if errors:raise SystemExit(2)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--timing-root",type=Path)
    p.add_argument("--shift-root",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.timing_root:
        r=timing_audit(a.timing_root,a.out/"timing")
        print(json.dumps({"timing":r},ensure_ascii=False))
    if a.shift_root:
        r=per_client_audit(a.shift_root,a.out/"per_client")
        print(json.dumps({"per_client":r},ensure_ascii=False))
if __name__=="__main__":main()
