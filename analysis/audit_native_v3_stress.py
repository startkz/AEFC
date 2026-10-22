#!/usr/bin/env python3
"""Independent full-trace audit of v3 independent red-team stress tests, not confirmation.
A workflow SUCCESS means that data were executed/audited, NOT that G3 was proved.
"""
import csv
import json
import math
from pathlib import Path
from statistics import mean

ROOT = Path("results/p0_stress_download")
OUT = Path("results/p0_native_v3_stress/audit")
OUT.mkdir(parents=True, exist_ok=True)
SCENES = ("collusion", "persistent_bias", "checkpoint_tamper")
METHODS = ("AEFC-Unprivileged", "AEFC-Checkpoint", "AEFC-ContractiveReentry")
SEEDS = tuple(range(64, 72))
EPS = 0.001
HOLD = 20
SAMPLES = 480
POST = 44
rows = []
errors = []

def norm(a, b):
    return math.sqrt(sum((float(x)-float(y))**2 for x, y in zip(a, b)))

def eps20(errors, post):
    for k in range(post, len(errors)-HOLD+1):
        if all(v <= EPS for v in errors[k:k+HOLD]):
            return k
    return None

for scene in SCENES:
    matches = sorted(ROOT.glob("AEFC-Stress-" + scene + "-*"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {scene} source artifact, got {len(matches)}")
    folder = matches[0]
    source = list(csv.DictReader((folder/"summary.csv").open()))
    if len(source) != 24:
        raise RuntimeError(f"{scene}: expected 24 original summary rows; got {len(source)}")
    sr = {(x["method"], int(x["seed"])): x for x in source}
    if set(sr) != {(m,s) for m in METHODS for s in SEEDS}:
        raise RuntimeError(f"{scene}: missing, duplicated, or unexpected method/seed")
    for method in METHODS:
        for seed in SEEDS:
            fp = folder/method/f"seed_{seed:02d}.jsonl"
            summary = folder/method/f"seed_{seed:02d}.summary.json"
            if not fp.is_file() or not summary.is_file():
                raise RuntimeError(f"Missing complete raw evidence: {fp} / {summary}")
            trace = [json.loads(line) for line in fp.read_text().splitlines() if line.strip()]
            if len(trace) != SAMPLES:
                raise RuntimeError(f"{fp}: only {len(trace)} samples, expected {SAMPLES}")
            if any(t["method"]!=method or int(t["seed"])!=seed or t["scenario"]!=scene for t in trace):
                raise RuntimeError(f"{fp}: inconsistent identity")
            if any(trace[i]["time"] >= trace[i+1]["time"] for i in range(SAMPLES-1)):
                raise RuntimeError(f"{fp}: time not strictly increasing")
            deployed = [t["deployed_theta"] for t in trace]
            shadow = [t["clean_shadow_theta"] for t in trace]
            proxy = [t["online_proxy_theta"] for t in trace]
            cp = [t["checkpoint_theta"] for t in trace]
            e = [norm(x,y) for x,y in zip(deployed,shadow)]
            dcp = [norm(x,y) for x,y in zip(deployed,cp)]
            p_err = [norm(x,y) for x,y in zip(deployed,proxy)]
            if any(not math.isfinite(v) for v in e+dcp+p_err):
                raise RuntimeError(f"{fp}: nonfinite reference error")
            if max(e[:15]) > 1e-9:
                raise RuntimeError(f"{fp}: online deployed and same-operator shadow differ before attack")
            if any(not t["checkpoint_valid"] for t in trace[10:]):
                raise RuntimeError(f"{fp}: invalid checkpoint snapshot")
            if scene != "checkpoint_tamper":
                if max(norm(x,cp[10]) for x in cp[10:]) > 1e-10:
                    raise RuntimeError(f"{fp}: unexpected checkpoint mutation")
            else:
                if max(norm(x,cp[10]) for x in cp[10:20]) > 1e-10:
                    raise RuntimeError(f"{fp}: early checkpoint mutation")
                if max(abs(norm(x,cp[10])-0.12) for x in cp[20:]) > 1e-8:
                    raise RuntimeError(f"{fp}: absent or wrong tamper magnitude")
            expected_case = {"collusion":1,"persistent_bias":2,"checkpoint_tamper":3}[scene]
            active_end = 180 if scene=="persistent_bias" else 43
            active_start = 20 if scene=="checkpoint_tamper" else 15
            if any(int(t["stress_case"])!=expected_case for t in trace):
                raise RuntimeError(f"{fp}: stress case mismatch")
            if any(bool(t["stress_active"])!=(active_start<=i<=active_end) for i,t in enumerate(trace)):
                raise RuntimeError(f"{fp}: stress injection activation mismatch")
            if scene=="checkpoint_tamper" and any(bool(t["checkpoint_tampered"])!=(i>=20) for i,t in enumerate(trace)):
                raise RuntimeError(f"{fp}: checkpoint tamper log mismatch")
            post=181 if scene=="persistent_bias" else POST
            if max(abs(e[i]-float(trace[i]["theta_reference_error"])) for i in range(SAMPLES)) > 1e-9:
                raise RuntimeError(f"{fp}: shadow error inconsistent with raw parameters")
            if max(abs(dcp[i]-float(trace[i]["checkpoint_distance"])) for i in range(SAMPLES)) > 1e-9:
                raise RuntimeError(f"{fp}: checkpoint error inconsistent with raw parameters")
            if max(abs(p_err[i]-float(trace[i]["online_proxy_distance"])) for i in range(SAMPLES)) > 1e-9:
                raise RuntimeError(f"{fp}: proxy error inconsistent with raw parameters")
            if method in ("AEFC-OnlineRelearn","AEFC-ContractiveReentry") and scene!="clean" and max(norm(proxy[i],shadow[i]) for i in range(15,44))<1e-12:
                raise RuntimeError(f"{fp}: suspicious oracle-equivalent online target")
            if abs(float(sr[(method,seed)]["theta_error_at_end"])-e[-1]) > 1e-9:
                raise RuntimeError(f"{fp}: original CSV end error mismatch")
            if abs(float(sr[(method,seed)]["online_proxy_distance_final"])-p_err[-1]) > 1e-9:
                raise RuntimeError(f"{fp}: original CSV proxy metric mismatch")
            phases = [int(t["recovery_phase"]) for t in trace]
            accepted = [bool(t["adapt_accepted"]) for t in trace]
            teacher_acc = [bool(t["online_proxy_accepted"]) for t in trace]
            violations = sum(not bool(t["safe_native_envelope"]) for t in trace)
            state_l1 = mean(sum(abs(x) for x in t["observation_normalized"]) for t in trace)
            action_l2 = mean(math.sqrt(sum(x*x for x in t["executed_correction"])) for t in trace)
            # Count every 10-step window with an error initially above epsilon;
            # no selected best window, interpolation, filtering or artificial
            # replacement of the dynamic offline same-plant clean target.
            windows = [(i, e[i+10]/e[i]) for i in range(post, SAMPLES-10) if e[i]>EPS]
            contracting_windows = sum(r<1.0-1e-10 for _,r in windows)
            adjacent = [(i, e[i+1]/e[i]) for i in range(post, SAMPLES-1) if e[i]>EPS]
            reductions = sum(r<1.0-1e-10 for _,r in adjacent)
            consecutive = 0; longest = 0
            for i in range(post, SAMPLES-1):
                if e[i]>EPS and e[i+1]<e[i]-1e-10:
                    consecutive+=1
                    longest=max(longest,consecutive)
                else:
                    consecutive=0
            first = eps20(e,post)
            row=dict(scenario=scene,method=method,seed=seed,
                     reference="OFFLINE dynamic same-physical-path clean shadow; NEVER online controller",
                     error_initial=e[post],error_final=e[-1],
                     error_reduction=e[post]-e[-1],
                     error_ratio_final=(e[-1]/e[post] if e[post]>1e-12 else ""),
                     online_proxy_error_final=norm(proxy[-1],shadow[-1]),
                     online_proxy_distance_final=p_err[-1],
                     checkpoint_distance_final=dcp[-1],
                     post_accepted=sum(accepted[post:]),
                     post_teacher_updates=sum(teacher_acc[post:]),
                     recovery_phase2_samples=sum(v==2 for v in phases[post:]),
                     recovery_phase3_samples=sum(v==3 for v in phases[post:]),
                     initial_outside=int(e[post]>EPS),
                     first_epsilon20_sample=first if first is not None else "",
                     genuinely_corrected=int(e[post]>EPS and first is not None),
                     ten_step_windows=len(windows),ten_step_contracting_windows=contracting_windows,
                     ten_step_contraction_fraction=(contracting_windows/len(windows) if windows else ""),
                     worst_ten_step_ratio=(max(r for _,r in windows) if windows else ""),
                     adjacent_above_epsilon=len(adjacent),
                     adjacent_reductions=reductions,
                     longest_strict_decrease_steps=longest,
                     physical_response_L1=state_l1,control_effort_L2=action_l2,
                     sampled_safety_violations=violations,
                     report_inliers_min=min(t["online_proxy_inliers"] for t in trace[post:]))
            rows.append(row)

assert len(rows)==72
with (OUT/"per_seed.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]))
    w.writeheader();w.writerows(rows)

def avg(rs,key):
    return mean(float(r[key]) for r in rs)

tables=[]
for scene in SCENES:
    for method in METHODS:
        rr=[r for r in rows if r["scenario"]==scene and r["method"]==method]
        tables.append(dict(scenario=scene,method=method,seeds=len(rr),
                           initial_outside=sum(r["initial_outside"] for r in rr),
                           genuinely_corrected=sum(r["genuinely_corrected"] for r in rr),
                           initial_shadow_error=avg(rr,"error_initial"),
                           final_shadow_error=avg(rr,"error_final"),
                           final_proxy_shadow_gap=avg(rr,"online_proxy_error_final"),
                           mean_accepted_post=avg(rr,"post_accepted"),
                           mean_phase2_samples=avg(rr,"recovery_phase2_samples"),
                           mean_phase3_samples=avg(rr,"recovery_phase3_samples"),
                           mean_physical_response_L1=avg(rr,"physical_response_L1"),
                           mean_control_effort_L2=avg(rr,"control_effort_L2"),
                           safety_violations=sum(r["sampled_safety_violations"] for r in rr)))
with (OUT/"summary.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(tables[0]))
    w.writeheader();w.writerows(tables)

result={
  "stage":"NEGATIVE RED-TEAM STRESS: exploratory robustness and failure limits, no G3/G5 certification",
  "native_backend":"MathWorks R2024b IEEE39 (must verify workflow logs)",
  "source":"only original workflow-uploaded seed traces",
  "episodes":72,"samples":72*SAMPLES,
  "seeds":"64..71","steps_per_episode":SAMPLES,
  "attack_windows":{"collusion":[15,43],"persistent_bias":[15,180],"checkpoint_tamper":[20,43]},
  "epsilon":EPS,"hold_steps":HOLD,
  "reference":"offline dynamic same-operator/same-physical-observation clean shadow",
  "online_target":"independently computed consensus proxy with conditional anchor-proximal contraction, not an oracle",
  "clean_shadow_operator":"mode-specific clean same-plant policy update; new mode4 includes the SAME proximal regularizer",
  "frozen_contractivity_gain":0.08,
  "meaning_of_success":"stress-specific re-entry only after actual stress end; not frozen confirmation, no global contraction",
  "previous_180_runs_unchanged":True,
  "cannot_certify":["full policy-network G3", "certified fixed clean optimum",
                    "global contraction factor", "independent physical state estimator",
                    "checkpoint cryptographic integrity", "G5 continuous-time CBF-QP"],
  "by_cell":tables}
(OUT/"audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
print(json.dumps(result,indent=2,ensure_ascii=False))
