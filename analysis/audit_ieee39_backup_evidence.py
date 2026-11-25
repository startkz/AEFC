#!/usr/bin/env python3
"""Independent source-preserving IEEE39 native physical/fallback forensic audit.

Reads ONLY original MathWorks R2024b JSONL produced by commit
30eb3a58bf9d092e1303e7be3492b36f6458382e. No simulation rerun and
no modification of original benchmark files.

A sampled ten-generator-speed observation is neither whole-system safety
nor a verified backup-governor reachability certificate.
"""
import argparse
import csv
import json
import math
from pathlib import Path

EXPECTED_SHA="30eb3a58bf9d092e1303e7be3492b36f6458382e"
DELTA=1.0/60.0
ATTACK_FIRST=15
ATTACK_LAST=89
RECOVERY_TH=0.25
SAMPLED_SAFE_TH=1.0
TEN_SCALE=0.02

def read_case(path):
    manifest=json.loads((path/"manifest.json").read_text())
    assert manifest["source_commit"]==EXPECTED_SHA
    assert manifest["all_ten_generators_speed_monitored"] is True
    assert manifest["full_state_certified"] is False
    rows=list(csv.DictReader((path/"summary.csv").open()))
    assert manifest["rows"]==len(rows)
    assert len(rows)>0
    traces={}
    audit=dict(
       experiment=path.name,experiment_commit=EXPECTED_SHA,
       episodes=len(rows),samples=0,attack_active_samples=0,
       alarm_cases=0,completed_hold_20_recovery_cases=0,
       all_ten_speed_envelope_violations=0,refused_additional_pref_samples=0,
       extra_pref_released_samples=0,
       largest_native_ten_speed_normalized=0.0,
       largest_postshield_attack_absolute=0.0,
       largest_extra_pref_absolute=0.0,
       all_checked_true_physical_paths=10,
       global_network_state_certified=False,
       continuous_intersample_safe_certified=False,
       emergency_governor_safe_certified=False,
       full_state_reachability_certified=False,
       all_methods={},reason_no_recovery=None,
    )
    for r in rows:
        scale=float(r["attack_scale"])
        seed=int(r["seed"]);method=r["method"];scene=r["scenario"]
        fp=path/f"scale_{scale:g}"/scene/method/f"seed_{seed:02d}.jsonl"
        assert fp.is_file(),fp
        trace=[json.loads(line) for line in fp.read_text().splitlines()]
        assert len(trace)==181,(fp,len(trace))
        assert all(x["commit_sha"]==EXPECTED_SHA for x in trace)
        assert all(int(x["seed"])==seed and x["method"]==method and
                   x["scenario"]==scene and abs(float(x["attack_scale"])-scale)<1e-12
                   for x in trace)
        base=[float(z) for z in trace[0]["all_ten_generator_speed_native"]]
        assert len(base)==10 and all(math.isfinite(z) for z in base)
        exposed=False
        running=[]
        largest=0.0
        for i,x in enumerate(trace):
            assert abs(float(x["time"])-i*DELTA)<1e-8,fp
            true=[float(z) for z in x["all_ten_generator_speed_native"]]
            reported=[float(z) for z in x["all_ten_generator_speed_normalized"]]
            online=[float(z) for z in x["native_speed"]]
            assert len(true)==len(reported)==10 and len(online)==4
            assert all(math.isfinite(z) for z in true+reported+online)
            assert max(abs(v-(s-b)/TEN_SCALE) for v,s,b in zip(reported,true,base))<2e-9
            speedmax=max(abs(z) for z in reported)
            largest=max(speedmax,largest)
            assert bool(x["sampled_all_ten_speed_inside_proxy"])==(speedmax<=SAMPLED_SAFE_TH+1e-9)
            audit["all_ten_speed_envelope_violations"]+=int(speedmax>SAMPLED_SAFE_TH+1e-9)
            audit["largest_native_ten_speed_normalized"]=max(
                audit["largest_native_ten_speed_normalized"],speedmax)
            assert not x["full_state_coverage"] and not x["full_state_certified"]
            corr=[float(z) for z in x["shield_action"]]
            attack=[float(z) for z in x["post_shield_attack"]]
            executed=[float(z) for z in x["executed_correction"]]
            assert len(corr)==len(attack)==len(executed)==4
            assert all(abs(a+c-e)<1e-9 for a,c,e in zip(attack,corr,executed))
            assert all(math.isfinite(z) for z in corr+attack+executed)
            attack_now=any(abs(z)>1e-12 for z in attack)
            should_attack=ATTACK_FIRST<=i<=ATTACK_LAST and scene in ("physical","joint")
            assert attack_now==should_attack,(fp,i,attack_now,should_attack)
            assert max(abs(z) for z in attack)<=0.024+1e-8
            audit["attack_active_samples"]+=int(attack_now)
            audit["largest_postshield_attack_absolute"]=max(
                audit["largest_postshield_attack_absolute"],max(abs(z) for z in attack))
            audit["largest_extra_pref_absolute"]=max(
                audit["largest_extra_pref_absolute"],max(abs(z) for z in corr))
            audit["samples"]+=1
            audit["refused_additional_pref_samples"]+=int(float(x["proxy_status"])<0)
            audit["extra_pref_released_samples"]+=int(bool(x["surrogate_released"]))
            if path.name=="strict":
                assert float(x["proxy_status"])<0 and not x["surrogate_released"]
                assert all(abs(z)<1e-15 for z in corr)
            if i==ATTACK_LAST:
                exposed=speedmax>RECOVERY_TH
            if i>ATTACK_LAST:running.append(speedmax)
        if exposed:
            audit["alarm_cases"]+=1
        successful=False
        if exposed:
            successful=any(max(running[k:k+20])<=RECOVERY_TH
                for k in range(0,len(running)-19))
        audit["completed_hold_20_recovery_cases"]+=int(successful)
        assert int(float(r["all_ten_speed_exposed_at_attack_stop"]))==int(exposed)
        assert int(float(r["all_ten_speed_strict_recovered"]))==int(successful)
        key=(scale,scene,seed,method)
        assert key not in traces
        traces[key]=trace
        group=audit["all_methods"].setdefault(method,{"episodes":0,"exposed":0,
             "recovered":0,"largest_normalized_speed":0.0})
        group["episodes"]+=1;group["exposed"]+=int(exposed)
        group["recovered"]+=int(successful)
        group["largest_normalized_speed"]=max(group["largest_normalized_speed"],largest)
    assert audit["samples"]==181*len(rows)
    assert audit["attack_active_samples"]==75*len(rows)
    if audit["alarm_cases"]==0:
        audit["reason_no_recovery"]="No sample was outside the preregistered recovery set at attack end"
    return audit,traces

def main(smoke,strict,sixmethod,output):
    a,A=read_case(smoke)
    b,B=read_case(strict)
    c,C=read_case(sixmethod)
    assert len(A)==16 and len(B)==8 and len(C)==24,(len(A),len(B),len(C))
    assert {k[3] for k in B}=={"AEFC-Full","Supervisor-only"}
    identical=0;maxdifference=0.0
    for (scale,scene,seed,method),x in B.items():
        if method!="AEFC-Full":continue
        y=B[(scale,scene,seed,"Supervisor-only")]
        assert len(x)==len(y)
        maxdelta=max(abs(v-w) for t,z in zip(x,y)
            for v,w in zip(t["all_ten_generator_speed_native"],
                           z["all_ten_generator_speed_native"]))
        maxdifference=max(maxdifference,maxdelta)
        if maxdelta==0:identical+=1
    assert identical==4,(identical,maxdifference)
    report=dict(
        original_source_sha256_manifest_required=True,
        replay_from_frozen_original_matlab_artifacts=True,
        original_experiment_commit=EXPECTED_SHA,
        smoke=a,strict=b,sixmethod=c,
        matched_strict_4_pairs_identical_10_generator_physical_trajectories=identical,
        max_absolute_ten_generator_speed_difference_under_strict_guard=maxdifference,
        triggered_postshield_attack_even_under_strict_guard=True,
        full_network_safety_certificate="NOT ESTABLISHED",
        control_fallback_claim=(
          "Strict refusal enforces zero added Pref correction and retains native "
          "governor paths; 10 physical rotor speeds were observed safe at discrete "
          "samples, BUT neither complete electrical-network safety nor continuous "
          "intersample governor viability is established"),
        interpretation=(
          "No attack-end-outside event occurred under frozen recovery criterion. "
          "Zero genuine recovery events; cannot estimate recovery-time benefit or "
          "claim six-method physical resilient recovery.")
    )
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--smoke",type=Path,required=True)
    p.add_argument("--strict",type=Path,required=True)
    p.add_argument("--sixmethod",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    k=p.parse_args()
    main(k.smoke,k.strict,k.sixmethod,k.output)
