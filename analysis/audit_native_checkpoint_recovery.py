#!/usr/bin/env python3
"""Independent audit of held-out native IEEE39 checkpoint/quarantine extension.
Must not silently discard any trajectories, alarms, expired checkpoints, or
unfavorable physical cost. Generates results only after 180 full traces exist.
"""
import csv,json,math,tarfile
from pathlib import Path
import numpy as np

ROOT=Path("results/p0_checkpoint_download")
OUT=Path("results/p0_native_checkpoint")
OUT.mkdir(parents=True,exist_ok=True)
SCEN={"clean":1,"knowledge":2,"joint":4}
MODES=("AEFC-Unprivileged","AEFC-Quarantine","AEFC-Checkpoint")
rows=[];errors=[]
EP=1e-3; HOLD=20
for scene,cod in SCEN.items():
    candidates=list(ROOT.glob(f"AEFC-Checkpoint-{scene}-*"))
    if len(candidates)!=1:raise RuntimeError((scene,len(candidates),[str(x) for x in candidates]))
    folder=candidates[0]
    summary_path=folder/"summary.csv"
    if not summary_path.exists():raise RuntimeError("Missing original summary "+str(summary_path))
    csvrows=list(csv.DictReader(summary_path.open()))
    if len(csvrows)!=60:raise RuntimeError(f"{scene}: expected 60 summaries, got {len(csvrows)}")
    for a in csvrows:
        method=a["method"];seed=int(a["seed"])
        if method not in MODES or not (20<=seed<=39):raise RuntimeError("Unexpected method/seed")
        f=folder/method/f"seed_{seed:02d}.jsonl"
        sf=folder/method/f"seed_{seed:02d}.summary.json"
        if not (f.exists() and sf.exists()):raise RuntimeError(f"Missing trace {f}")
        t=[json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        if len(t)!=220:raise RuntimeError(("Bad trajectory length",f,len(t)))
        if [z["time"] for z in t]!=sorted([z["time"] for z in t]):raise RuntimeError("Nonmonotonic")
        params=np.asarray([z["deployed_theta"] for z in t],float)
        shadow=np.asarray([z["clean_shadow_theta"] for z in t],float)
        ckpts=np.asarray([z["checkpoint_theta"] for z in t],float)
        err=np.linalg.norm(params-shadow,axis=1)
        cd=np.linalg.norm(params-ckpts,axis=1)
        if max(abs(err-np.asarray([z["theta_reference_error"] for z in t],float)))>1e-9:raise RuntimeError("Shadow mismatch")
        if max(abs(cd-np.asarray([z["checkpoint_distance"] for z in t],float)))>1e-9:raise RuntimeError("Checkpoint mismatch")
        if not all(z["checkpoint_valid"] for z in t[10:]):raise RuntimeError("Missing commissioning snapshot")
        if np.max(abs(ckpts[11:]-ckpts[10]))>1e-10:raise RuntimeError("Checkpoint mutated")
        scatter=np.asarray([z["detector_scatter"] for z in t])
        alarm=np.asarray([z["alert_latched"] for z in t],bool)
        phases=np.asarray([z["recovery_phase"] for z in t],int)
        first_alert=int(np.where(alarm)[0][0]) if alarm.any() else None
        first_recover=int(np.where(phases==3)[0][0]) if (phases==3).any() else None
        accepted=np.asarray([z["adapt_accepted"] for z in t],bool)
        state=np.asarray([z["observation_normalized"] for z in t],float)
        action=np.asarray([z["executed_correction"] for z in t],float)
        if np.any(~np.isfinite(state)) or np.any(~np.isfinite(action)):raise RuntimeError("Nonfinite observations")
        fail_ckpt=0
        if method=="AEFC-Checkpoint":
            for i in range(1,len(t)):
                if phases[i]==2:
                    if cd[i] > 0.5*cd[i-1]+1e-10:
                        fail_ckpt+=1
                if phases[i]==3 and cd[i]>1e-10:
                    fail_ckpt+=1
            if fail_ckpt:raise RuntimeError((f,"Violation of checkpoint contract",fail_ckpt))
        if method=="AEFC-Quarantine" and np.any(np.diff(phases)<0):
            # Alarm resumes phase1 on repeated suspicious inputs; monotonic phase is not required.
            pass
        if method=="AEFC-Unprivileged" and any(alarm):raise RuntimeError("No-intervention policy activated rollback")
        # Certified metric ONLY checkpoint distance; dynamic shadow remains separate.
        post=cd[44:]
        complete=None
        for i in range(len(post)-HOLD+1):
            if np.all(post[i:i+HOLD]<=EP):
                complete=i;break
        loss=np.sum(np.abs(state),axis=1)
        controls=np.linalg.norm(action,axis=1)
        row={"scenario":scene,"seed":seed,"method":method,
             "first_alarm_step":first_alert if first_alert is not None else "",
             "first_completed_step":first_recover if first_recover is not None else "",
             "alarm_by_attack_end":int(scene!="clean" and first_alert is not None and first_alert<=43),
             "false_alarm_in_clean":int(scene=="clean" and first_alert is not None),
             "checkpoint_distance_at_attack_end":float(cd[43]),
             "checkpoint_distance_post_first":float(cd[44]),
             "checkpoint_distance_final":float(cd[-1]),
             "checkpoint_first_eps20":complete if complete is not None else "",
             "checkpoint_post_corrected":int(post[0]>EP and complete is not None),
             "shadow_error_final":float(err[-1]),
             "accepted_post":int(accepted[44:].sum()),
             "normalized_state_L1_mean":float(loss.mean()),
             "normalized_state_L1_attack_post_mean":float(loss[44:].mean()),
             "executed_action_L2_mean":float(controls.mean()),
             "native_recovery_set_exits":int(np.sum(np.max(np.abs(state),axis=1)>.25)),
             "native_safety_envelope_violations":int(np.sum(np.max(np.abs(state),axis=1)>1)),
             "detector_score_max_clean_window":float(max(scatter[:15].max(),scatter[44:].max())),
             "detector_score_max_attack_window":float(scatter[15:44].max()),
             "contract_failure_steps":fail_ckpt}
        # Protect against wrong original summary / sample data.
        if abs(float(a["checkpoint_distance_final"])-row["checkpoint_distance_final"])>1e-9:raise RuntimeError("Summary mismatch")
        if abs(float(a["mean_normalized_state_l1"])-row["normalized_state_L1_mean"])>1e-9:raise RuntimeError("Cost mismatch")
        rows.append(row)
assert len(rows)==180,(len(rows),"expected 3x3x20")
with (OUT/"per_seed.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
cols=[]
for scene in SCEN:
    for mode in MODES:
        rr=[r for r in rows if r["scenario"]==scene and r["method"]==mode]
        cols.append({"scenario":scene,"method":mode,"seeds":len(rr),
                     "alarm_during_attack":sum(r["alarm_by_attack_end"] for r in rr),
                     "false_alarm_clean":sum(r["false_alarm_in_clean"] for r in rr),
                     "checkpoint_corrected_post":sum(r["checkpoint_post_corrected"] for r in rr),
                     "checkpoint_eps20_reached":sum(r["checkpoint_first_eps20"]!="" for r in rr),
                     "checkpoint_distance_final_mean":float(np.mean([r["checkpoint_distance_final"] for r in rr])),
                     "shadow_error_final_mean":float(np.mean([r["shadow_error_final"] for r in rr])),
                     "mean_normalized_response_L1":float(np.mean([r["normalized_state_L1_mean"] for r in rr])),
                     "mean_action_L2":float(np.mean([r["executed_action_L2_mean"] for r in rr])),
                     "safety_sample_violations":sum(r["native_safety_envelope_violations"] for r in rr),
                     "post_accepted_mean":float(np.mean([r["accepted_post"] for r in rr]))})
with (OUT/"summary.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(cols[0]));w.writeheader();w.writerows(cols)
report={"native_backend":"MATLAB R2024b IEEE39","previous_main_unchanged":True,
        "run_source":"workflow job artifacts", "evaluation":"held-out seeds 20..39",
        "exploration":"threshold 0.35 calibrated on prior seeds 0..19",
        "episodes":len(rows),"samples":len(rows)*220,"attack_window":[15,43],
        "epsilon":EP,"hold_samples":HOLD,
        "checkpoint_created_at_step":10,
        "checkpoint_certificate_scope":"locally isolated pre-attack commissioning copy, NOT cryptographic attestation",
        "unprivileged_controller":"online risk excludes oracle cleanBelief; provenance flags not read by live PATBU",
        "limitations":["plant reports synthetically derived from simulated physical truth",
                       "dynamic clean shadow is NOT a fixed certified training optimum",
                       "case-specific report-divergence detector and local checkpoint only",
                       "continuous-time CBF-QP contract not verified"],
        "results":cols}
(OUT/"audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
print(json.dumps(report,indent=2,ensure_ascii=False))
