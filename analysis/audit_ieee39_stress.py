#!/usr/bin/env python3
"""Independent native IEEE39 physical *stress* recovery experiment audit.

DO NOT use this as evidence of full 39-bus/branch thermal or voltage safety.
Stress >0.024 pu explicitly exceeds previous original P0 input bound.
A complete AEFC vs Supervisor recovery claim requires eligible attack-end
physically OUTSIDE events, 20-sample holds, independent seeds, same terminal
proxy supervisor and a predeclared effect-size/uncertainty comparison.
"""
from __future__ import annotations
import argparse,csv,json,math,random,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STRESS=ROOT/"configs/ieee39_stress_protocol_r1.json"

def close(a,b,tol=2e-8):return abs(a-b)<=tol
def bootstrap_diffs(byseed,rounds=6000):
    # Unit of resampling is the independently paired SEED.
    keys=sorted(byseed)
    vals=[statistics.mean(byseed[x]) for x in keys]
    if not vals:return dict(n_seeds=0,mean=None,ci95=None,estimated=False)
    rng=random.Random(20261125)
    bs=[statistics.mean(vals[rng.randrange(len(vals))] for _ in vals) for _ in range(rounds)]
    bs.sort()
    return dict(n_seeds=len(vals),mean=statistics.mean(vals),
                ci95=[bs[int(.025*rounds)],bs[min(rounds-1,int(.975*rounds))]],
                percentiles_derived_from_independent_seeds=len(vals)>=10)

def inspect(directory:Path,out:Path):
    spec=json.loads(STRESS.read_text())
    manifest=json.loads((directory/"manifest.json").read_text())
    rows=list(csv.DictReader((directory/"summary.csv").open()))
    assert manifest["rows"]==len(rows)>0
    assert manifest["stress_attack_not_original_certified_bound"] is True
    assert manifest["full_IEEE39_state_safety_verified"] is False
    assert manifest["full_state_certified"] is False
    assert manifest["all_ten_generators_speed_monitored"] is True
    assert manifest["pref_setpoint_interposition_monitored"] is True
    assert manifest["unaltered_native_solver_time_physical_monitor"] is True
    assert manifest["original_governor_backup_certified"] is False
    predeclared={float(z) for z in spec["physical_pref_stress_amplitudes"]}
    instances={};byseed={}
    aggregate=dict(cases=0,samples=0,pressure_cases_above_original_bound=0,
                   attacked_samples=0,proxy_releases=0,proxy_refusals=0,
                   ten_speed_sampled_violations=0,raw_solver_speed_violations=0,
                   true_exposed=0,true_recovered=0,
                   actual_max_ten_generator_speed=0.,
                   max_abs_setpoint_interposition_error=0.,
                   original_governor_reference_paths_count=4)
    for row in rows:
        amp=float(row["attack_scale"]);seed=int(row["seed"])
        scene=row["scenario"];method=row["method"]
        assert any(close(amp,x) for x in predeclared)
        assert scene in spec["threat_attacks"]
        trace_path=directory/f"scale_{amp:g}"/scene/method/f"seed_{seed:02d}.jsonl"
        raw_path=directory/f"scale_{amp:g}"/scene/method/f"seed_{seed:02d}.raw-solver.jsonl"
        trace=[json.loads(l) for l in trace_path.read_text().splitlines()]
        raw=[json.loads(l) for l in raw_path.read_text().splitlines()]
        assert len(trace)==181 and len(raw)>=2
        amp_outside_original=amp>spec["hard_constraints"]["original_P0_postshield_upper"]
        aggregate["pressure_cases_above_original_bound"]+=int(amp_outside_original)
        base=list(map(float,trace[0]["all_ten_generator_speed_native"]))
        assert len(base)==10
        maxnorms=[];exposed=False
        for i,r in enumerate(trace):
            assert close(float(r["time"]),i/60,1e-8)
            assert r["method"]==method and r["scenario"]==scene and int(r["seed"])==seed
            assert not r["full_state_certified"] and not r["full_state_coverage"]
            assert r["surrogate_released"] == (r["proxy_status"]>0)
            attack=list(map(float,r["post_shield_attack"]))
            delivered=list(map(float,r["native_delivered_pref_reference"]))
            nativebase=list(map(float,r["original_governor_pref_reference"]))
            correction=list(map(float,r["shield_action"]))
            residual=[d-b-c-a for d,b,c,a in zip(delivered,nativebase,correction,attack)]
            assert all(len(x)==4 for x in [attack,delivered,nativebase,correction,residual])
            assert max(map(abs,residual))<3e-6
            assert max(map(abs,attack))<=amp+1e-8
            active=15<=i<=89
            assert active == (max(map(abs,attack))>1e-12), (trace_path,i)
            if active:
                assert all(close(abs(a),amp,2e-8) for a in attack)
            else:
                assert all(abs(a)<1e-12 for a in attack)
            speeds=list(map(float,r["all_ten_generator_speed_native"]))
            norm=list(map(float,r["all_ten_generator_speed_normalized"]))
            assert len(speeds)==len(norm)==10
            assert max(abs((v-b)/.02-z) for v,b,z in zip(speeds,base,norm))<2e-9
            maxval=max(map(abs,norm));maxnorms.append(maxval)
            assert (maxval<=1+1e-9) == bool(r["sampled_all_ten_speed_inside_proxy"])
            aggregate["ten_speed_sampled_violations"]+=int(maxval>1)
            aggregate["attacked_samples"]+=int(active)
            aggregate["proxy_releases"]+=int(r["surrogate_released"])
            aggregate["proxy_refusals"]+=int(float(r["proxy_status"])<0)
            aggregate["max_abs_setpoint_interposition_error"]=max(aggregate["max_abs_setpoint_interposition_error"],max(map(abs,residual)))
            aggregate["actual_max_ten_generator_speed"]=max(aggregate["actual_max_ten_generator_speed"],maxval)
        assert close(float(raw[0]["time"]),0,1e-8)
        assert close(float(raw[-1]["time"]),3,1e-7)
        assert all(raw[i+1]["time"]>raw[i]["time"] for i in range(len(raw)-1))
        rawviol=sum(max(map(abs,r["all_ten_speed_normalized"]))>1+1e-9 for r in raw)
        aggregate["raw_solver_speed_violations"]+=rawviol
        outside=maxnorms[89]>.25
        first=next((i for i in range(90,len(trace)-19)
                    if all(v<=.25 for v in maxnorms[i:i+20])),None) if outside else None
        recovered=first is not None
        assert (row["all_ten_speed_exposed_at_attack_stop"]=="1")==outside
        assert (row["all_ten_speed_strict_recovered"]=="1")==recovered
        if recovered:
            assert close(float(row["all_ten_speed_recovery_time"]),(first-89)/60)
        assert int(float(row["raw_solver_speed_monitor_samples"]))==len(raw)
        assert int(float(row["raw_solver_ten_speed_violation_count"]))==rawviol
        assert int(float(row["proxy_release_count"]))==sum(t["surrogate_released"] for t in trace)
        assert not int(float(row["full_state_certified_count"]))
        key=(amp,scene,seed,method)
        assert key not in instances
        instances[key]=dict(max_speed=max(maxnorms),mean_speed=statistics.mean(maxnorms),
                            area_speed=sum(maxnorms)/60,
                            exposed=outside,recovered=recovered,
                            recovery_time=(first-89)/60 if recovered else None,
                            sample_speed_violations=sum(v>1 for v in maxnorms),
                            raw_solver_speed_violations=rawviol)
        aggregate["cases"]+=1;aggregate["samples"]+=len(trace)
        aggregate["true_exposed"]+=outside
        aggregate["true_recovered"]+=recovered
    assert aggregate["samples"]==aggregate["cases"]*181
    assert aggregate["attacked_samples"]==aggregate["cases"]*75
    pairs=[];effectbyseed={}
    for (amp,scene,seed,method),a in instances.items():
        if method!="AEFC-Full":continue
        b=instances.get((amp,scene,seed,"Supervisor-only"))
        if not b:continue
        d=b["mean_speed"]-a["mean_speed"]  # positive means AEFC lower speed error
        effects=dict(pressure=amp,scenario=scene,seed=seed,
                    both_at_attack_end_exposed=bool(a["exposed"] and b["exposed"]),
                    ae_fc_exposed=bool(a["exposed"]),supervisor_exposed=bool(b["exposed"]),
                    ae_fc_recovered=bool(a["recovered"]),supervisor_recovered=bool(b["recovered"]),
                    ae_fc_speed_error=a["mean_speed"],
                    supervisor_speed_error=b["mean_speed"],
                    supervisor_minus_ae_fc_speed_error=d,
                    ae_fc_recovery_time=a["recovery_time"],
                    supervisor_recovery_time=b["recovery_time"])
        pairs.append(effects);effectbyseed.setdefault(seed,[]).append(d)
    effect=bootstrap_diffs(effectbyseed)
    report=dict(
        source="original actual MathWorks IEEE39BusSystem native Simulink stress copy",
        source_sha=manifest["source_commit"],
        preregistered_spec="configs/ieee39_stress_protocol_r1.json",
        full_network_safety_certified=False,
        original_attack_budget_incompatible_with_larger_stresses=True,
        actual_native_experiment_audit=aggregate,
        method_by_condition={str(k):v for k,v in sorted(instances.items())},
        paired_ae_fc_supervisor=pairs,
        paired_seed_cluster_effect=effect,
        genuine_recovery_effect_demonstrated=False,
        reason_for_no_automatic_promotion=(
            "Only 10 rotor speeds are physically monitored, no 39-bus/branch full-state "
            "certificate, exploratory attacks exceed original 0.024 bound, and a "
            "non-zero attack-end-exposure with paired 20-sample hold plus independent "
            "replicated benefit is required for physical recovery claim."
        ))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["actual_native_experiment_audit","paired_seed_cluster_effect"]},indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    inspect(a.results,a.output)
