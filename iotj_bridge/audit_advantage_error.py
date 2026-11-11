#!/usr/bin/env python3
"""Fail-closed frozen-model paired-rollout local advantage-error evidence audit.

No trained model or control action is modified. Paired finite-horizon returns
from a deterministic AC environment are empirical current-policy targets,
not optimal Q* and not uniform convergence or sign guarantees.
"""
import argparse,csv,json,math
from pathlib import Path
import numpy as np

SEEDS=tuple(range(80,90))
SOURCE="0af6e066ff385b191b2db3b86a40adc2ad79956f"
def require(x,s):
    if not x:raise ValueError(s)
def mean_ci(x,seed):
    a=np.asarray(x,dtype=float)
    require(len(a)==10,"Ten training seeds required")
    rng=np.random.default_rng(seed)
    p=a[rng.integers(0,10,size=(10000,10))].mean(axis=1)
    return float(a.mean()),float(np.quantile(p,.025)),float(np.quantile(p,.975))
def check(s,p):
    require(int(s["seed"]) in SEEDS,"Unknown seed")
    require(s["source_git_commit"]==SOURCE,"Source checkpoint mismatch")
    require(s["global_error_guarantee"] is False,"Unsupported uniform guarantee")
    require(s["samples"]>=20,"Insufficient paired physical samples")
    require(len(s["checkpoint_sha256"])==64,"Missing checkpoint hash")
    with p.open("r",newline="",encoding="utf8") as f:
        rs=list(csv.DictReader(f))
    require(len(rs)==int(s["samples"]),"Diagnostic row count mismatch")
    for r in rs:
        require(int(r["seed"])==int(s["seed"]),"Mixed training seeds")
        require(r["source_git_commit"]==SOURCE,"Wrong checkpoint source")
        require(r["checkpoint_sha256"]==s["checkpoint_sha256"],"Incorrect per-row checkpoint hash")
        hat=float(r["estimated_advantage"])
        mc=float(r["paired_finite_horizon_advantage"])
        require(all(math.isfinite(float(r[k])) for k in (
            "estimated_advantage","paired_finite_horizon_advantage",
            "mc_return_behavior","mc_return_policy","qhat_behavior","qhat_policy")),
            "Nonfinite advantage")
        require(abs((hat-mc)-float(r["estimated_minus_paired"]))<1e-7,
                "Mismatched estimated difference")
        require(abs(abs(hat-mc)-float(r["abs_adv_error"]))<1e-7,
                "Mismatched absolute advantage error")
        require(abs((float(r["qhat_behavior"])-float(r["qhat_policy"]))-hat)<1e-7,
                "Critic advantage arithmetic mismatch")
        require(abs((float(r["mc_return_behavior"])-float(r["mc_return_policy"]))-mc)<1e-7,
                "Physical paired-return arithmetic mismatch")
        require(int(r["false_positive_advantage"])==int(hat>0 and mc<=0),
                "Wrong false positive selection")
        require(int(r["sign_mismatch"])==int((hat>0)!=(mc>0)),"Wrong empirical sign check")
        for th,k in ((.01,"near_estimated_zero_001"),
                     (.05,"near_estimated_zero_005"),
                     (.10,"near_estimated_zero_010")):
            require(int(r[k])==int(abs(hat)<=th),"Wrong margin near zero fraction")
        require(int(r["start_step"]) in (0,10),"Unregistered state checkpoint")
        require(int(r["profile"]) in (0,1),"Unregistered demand profile")
    require(abs(float(s["mean_abs_advantage_error"])-np.mean([float(r["abs_adv_error"]) for r in rs]))<1e-7,
            "Seed-level error mismatch")
    return rs
def run(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    errors=[];records={};all_rows=[]
    files=sorted(root.rglob("seed*.summary.json"))
    for path in files:
        try:
            s=json.loads(path.read_text())
            seed=int(s["seed"])
            require(seed not in records,"Duplicate training seed")
            rs=check(s,path.with_name(path.name.replace(".summary.json",".csv")))
            records[seed]=s;all_rows.extend(rs)
        except Exception as e:errors.append({"file":str(path),"reason":str(e)})
    missing=sorted(set(SEEDS)-set(records))
    passed=(len(records)==10 and not missing and not errors)
    report={"passed":passed,"expected_training_seeds":10,"audited_training_seeds":len(records),
            "total_paired_physical_samples":len(all_rows),
            "missing_seeds":missing,"errors":errors,
            "source_training_checkpoint_commit":SOURCE,
            "diagnostic":"paired deterministic AC current-policy finite-horizon physical returns",
            "not_established":"optimal Q*, uniform epsilon_Q, true-advantage sign guarantee, global aggregation return",
            "training_is_untouched":True}
    (out/"r4_adv_error_audit_report.json").write_text(json.dumps(report,indent=2)+"\n")
    if not passed:raise ValueError("Fail-closed advantage audit, see "+str(out))
    metrics=(
      "mean_abs_advantage_error","false_positive_fraction","sign_mismatch_fraction",
      "near_zero_fraction_abs_est_le_001","near_zero_fraction_abs_est_le_005",
      "near_zero_fraction_abs_est_le_010","max_empirical_abs_advantage_error")
    summary=[]
    for idx,key in enumerate(metrics):
        mean,lo,hi=mean_ci([float(records[seed][key]) for seed in SEEDS],20261111+idx*41)
        summary.append({"metric":key,"independent_training_seeds":10,
                        "mean":mean,"ci95_low":lo,"ci95_high":hi})
    pairs=[{
      "seed":seed,"source_commit":SOURCE,"checkpoint_sha256":records[seed]["checkpoint_sha256"],
      **{k:records[seed][k] for k in metrics},"n_samples":records[seed]["samples"]
    } for seed in SEEDS]
    def save(name,rows):
        with (out/name).open("w",newline="",encoding="utf8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save("r4_adv_error_per_seed.csv",pairs)
    save("r4_adv_error_per_sample.csv",all_rows)
    save("r4_adv_error_summary.csv",summary)
    report["interpretation"]="empirical errors conditional on sampled states/profiles; not valid sup bounds"
    (out/"r4_adv_error_audit_report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.root,a.out),indent=2))
