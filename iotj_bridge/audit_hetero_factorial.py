#!/usr/bin/env python3
"""Three-seed *exploratory* 2^3 physical-factor experiment audit.

Each full training seed is an independent unit. The adapter-frozen control
preserves the adapter architecture and only suppresses local adapter fitting.
Prototype-disabled suppresses alignment, not the server's prototype metadata.
No results are released without all 96 raw runs and SHA256 checkpoints.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math
import numpy as np

SEEDS=(80,81,82)
FACTORS=("base","dim","saturation","shift","dim_saturation","dim_shift",
         "saturation_shift","dim_saturation_shift")
CONTROLS=("adv","adapter_frozen","proto_alignment_off","dense")
EXPECTED={(s,f,c) for s in SEEDS for f in FACTORS for c in CONTROLS}
def require(v,s):
    if not v:raise ValueError(s)
def near(a,b,n,epsilon=1e-6):
    a,b=float(a),float(b)
    require(math.isfinite(a) and math.isfinite(b) and
            abs(a-b)<=epsilon*max(1.,abs(a),abs(b)),f"{n}: {a} != {b}")
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def save(p,rows):
    require(rows,"empty "+str(p))
    fields=sorted(set().union(*(r.keys() for r in rows)))
    with p.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def recovery(t):
    n=0
    for z in t:
        valid=bool(z["safe"]) and bool(z["ac_converged"]) and float(z["restored_pct"])>=90.
        n=n+1 if valid else 0
        if n>=5:return int(z["t"])-4
    return -1
def assess(p):
    d=json.loads(p.read_text())
    s=d["summary"];seed=int(s["seed"]);factor=s["hetero"]
    mode=s["method"];ap=int(s["disable_adapters"]);pr=int(s["disable_proto"])
    if mode=="dense" and not ap and not pr:ctrl="dense"
    elif mode=="adv" and not ap and not pr:ctrl="adv"
    elif mode=="adv" and ap and not pr:ctrl="adapter_frozen"
    elif mode=="adv" and not ap and pr:ctrl="proto_alignment_off"
    else:raise ValueError("Unexpected control ablation")
    key=(seed,factor,ctrl)
    require(key in EXPECTED,f"Unregistered factor cell {key}")
    expected_dims=[6,3,6,3,6] if "dim" in factor else [6]*5
    for k,v in {"case":39,"clients":5,"train_episodes":1000,"completed_rounds":200,
                "scheduled_rounds":200,"train_episode_records":1000,
                "eval_episodes":10,"steps_per_episode":30,"fed_sync_interval":5,
                "batch_size":256,"hidden_size":128,"latent_size":32,
                "local_fit_steps":5,"sharing_steps":2,
                "record_training_trace":1,"fixed_traffic":1,
                "malicious_clients":0,"disable_adapter_training":ap,
                "prototype_alignment_disabled":pr,
                "shared_backbone_parameters":24864}.items():
        require(int(s[k])==v,f"{key} wrong {k}")
    require(s["observation_dimensions"]==expected_dims,f"{key} observation dimension mismatch")
    require(s["per_client_encoder_parameters"]==[5024 if v==6 else 4640 for v in expected_dims],
            f"{key} encoder size mismatch")
    require(s["per_client_head_parameters"]==[4353]*5,f"{key} head geometry mismatch")
    near(s["kappa"],.2,f"{key} kappa",1.e-12)
    require(s["backend"]=="pandapower AC quasi-static" and s["attack"]=="clean" and
            s["weight_cap"]=="None",f"{key} attack/cap/platform")
    ckpt=p.with_suffix(".pt");meta=p.with_suffix(".manifest.json")
    require(ckpt.exists() and meta.exists(),f"{key} missing checkpoint")
    m=json.loads(meta.read_text())
    require(sha(p)==m["source_json_sha256"] and
            sha(ckpt)==m["checkpoint_sha256"],f"{key} source/checkpoint checksum mismatch")
    require(int(m["training_episodes_executed"])==1000,f"{key} incomplete budget")
    require(len(d["train_episodes"])==1000 and len(d["rounds"])==200 and
            len(d["tests"])==10,f"{key} incomplete raw trace")
    require(sum(int(z["uplink_bytes"]) for z in d["rounds"])==s["uplink_bytes"],
            f"{key} upload accounting mismatch")
    for z in d["rounds"]:
        require(sum(int(x) for x in z["actual_serialized_client_bytes"])==z["uplink_bytes"],
                f"{key} per-client byte accounting")
    success=[];load=[];censor=[];restricted=[];shift_checked=0
    for i,e in enumerate(d["train_episodes"],1):
        require(int(e["episode"])==i,f"{key} missing episode")
        trace=e["trace"]
        require(1<=len(trace)<=30 and len(trace)==e["steps_executed"],f"{key} invalid steps")
        expected=recovery(trace)
        require(expected==int(e["recovery_step"]) and
                int(e["censored"])==int(expected<0) and
                int(e["safe_dwell5"])==int(expected>=0),f"{key} safe dwell mismatch")
        near(trace[-1]["restored_pct"],e["recovery_accuracy_pct"],f"{key} final restored load")
        if len(trace)>=12:
            ratio_a=trace[10]["client_demand_ratio"]
            ratio_b=trace[11]["client_demand_ratio"]
            if "shift" in factor:
                for j in range(5):
                    near(ratio_b[j]/ratio_a[j],1.06 if j%2 else 1.0,
                         f"{key} demand intervention check",1.e-6)
            else:
                for j in range(5):
                    near(ratio_b[j]/ratio_a[j],1.0,
                         f"{key} unexpected demand shift",1.e-6)
            shift_checked+=1
        if "saturation" in factor:
            for j in (1,3):
                prev=.65
                for z in trace:
                    now=float(z["client_served_fraction"][j])
                    require(now-prev<=.018*.6+1.e-7,
                            f"{key} actuator 0.6 limit broken")
                    prev=now
        load.append(float(e["final_restored_pct"]))
        success.append(int(expected>=0))
        censor.append(int(expected<0))
        restricted.append(expected if expected>=0 else 31)
    require(shift_checked>0,f"{key} no episode reached demand-shift observation step")
    require(sum(int(t["safe_dwell5"]) for t in d["tests"])==s["safe_dwell_successes"],
            f"{key} heldout safety count")
    return key,{
        "seed":seed,"factor":factor,"control":ctrl,"git_commit":m["git_commit"],
        "mean_train_terminal_load_pct":float(np.mean(load)),
        "mean_train_safe_fraction":float(np.mean(success)),
        "mean_train_restricted_recovery_score":float(np.mean(restricted)),
        "right_censored_episodes":sum(censor),
        "heldout_terminal_load_pct":float(s["mean_test_load_pct"]),
        "heldout_safe_dwell_fraction":float(s["safe_dwell_successes"])/10.,
        "application_uplink_bytes":int(s["uplink_bytes"]),
        "recorded_operational_shift_episodes":shift_checked,
        "model_json_sha256":m["source_json_sha256"],
        "model_checkpoint_sha256":m["checkpoint_sha256"],
    }
def ci3(values,seed):
    a=np.asarray(values,dtype=float)
    require(len(a)==3,"Expect three paired seeds in pilot")
    g=np.random.default_rng(seed)
    draw=a[g.integers(0,3,size=(8000,3))].mean(1)
    return float(a.mean()),float(np.quantile(draw,.025)),float(np.quantile(draw,.975))
def run(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    records={};errors=[]
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith(".manifest.json"):continue
        try:
            key,data=assess(path)
            require(key not in records,"Duplicate experiment "+str(key))
            records[key]=data
        except Exception as e:errors.append({"file":str(path),"reason":str(e)})
    missing=sorted(EXPECTED-set(records))
    sha_list=sorted({r["git_commit"] for r in records.values()})
    if len(sha_list)!=1:errors.append({"reason":"Experiments do not share identical code SHA",
                                     "sha":sha_list})
    report={
        "passed":not(errors or missing or len(records)!=len(EXPECTED)),
        "expected_runs":len(EXPECTED),"audited_runs":len(records),
        "missing":missing,"errors":errors,"training_seeds":list(SEEDS),
        "git_source_shas":sha_list,"platform":"quasi-static AC IEEE39",
        "train_episodes_each":1000,"fed_rounds_each":200,
        "pilot_only":True,"not_justified":"ten-seed population significance or native Simulink inference",
        "censoring":"-1 for failure; 31 only a restricted comparison score",
        "adapter_freeze_means":"freeze local adapter training, not delete encoder/head",
        "prototype_off_means":"disable local alignment, not global prototype exchange"}
    (out/"r4_hetero_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    if not report["passed"]:raise ValueError("Hetero pilot fail closed; see audit report")
    save(out/"r4_hetero_per_seed.csv",[records[k] for k in sorted(records)])
    metrics=("mean_train_terminal_load_pct","mean_train_safe_fraction",
             "mean_train_restricted_recovery_score","heldout_terminal_load_pct",
             "heldout_safe_dwell_fraction","application_uplink_bytes")
    summary=[]
    for factor in FACTORS:
        for control in CONTROLS:
            cohort=[records[(seed,factor,control)] for seed in SEEDS]
            item={"factor":factor,"control":control,"n_training_seeds":3}
            for j,m in enumerate(metrics):
                mean,lo,hi=ci3([z[m] for z in cohort],20261111+j*100+len(summary))
                item.update({m+"_mean":mean,m+"_low95":lo,m+"_high95":hi})
            summary.append(item)
    save(out/"r4_hetero_summary.csv",summary)
    # Full 2^3 interaction coefficients, estimated per seed, NOT by pooling episodes.
    method_effects=[]
    for control in CONTROLS:
        for metric in ("heldout_terminal_load_pct","heldout_safe_dwell_fraction"):
            effects=[]
            for seed in SEEDS:
                y=lambda key:records[(seed,key,control)][metric]
                # All 3 factors' third order contrast, holding the same seed.
                effect=(y("dim_saturation_shift")-y("dim_saturation")
                        -y("dim_shift")-y("saturation_shift")
                        +y("dim")+y("saturation")+y("shift")-y("base"))
                effects.append(effect)
            mean,lo,hi=ci3(effects,20261111+len(method_effects)*57)
            method_effects.append({"control":control,"metric":metric,
                "effect":"dim_x_saturation_x_shift",
                "paired_training_seeds":3,
                "mean":mean,"bootstrap95_low":lo,"bootstrap95_high":hi})
    save(out/"r4_hetero_interactions.csv",method_effects)
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(run(args.root,args.out),indent=2))
