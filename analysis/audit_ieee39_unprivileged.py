#!/usr/bin/env python3
"""Independent audit of novel IEEE39 unprivileged experiment.
Full-state certificate is deliberately *not* claimed.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTROLLER=ROOT/'experiments/matlab/AEFCNativeController.m'
ATTACK=ROOT/'experiments/matlab/AEFCNativeAttackHarness.m'
BUILDER=ROOT/'experiments/matlab/aefc_ieee39_build_unprivileged.m'
CONFIG=ROOT/'configs/ieee39_unpriv_r1.json'

def static_audit():
    source=CONTROLLER.read_text()
    harness=ATTACK.read_text()
    builder=BUILDER.read_text()
    forbidden=('cleanBelief','provenance','attackActive','scenarioFlags','ScenarioCode',
               'thetaShadow','trueState','offlineClean','attackerIdentity')
    hits=[w for w in forbidden if w in source]
    assert not hits,('online-oracle-leak',hits)
    assert 'function [uShield,diagOut]=stepImpl(obj,localPhysical,packet)' in source
    assert 'function [packet,uPost]=stepImpl(obj,obsPhysical)' in harness
    assert 'aefc_native_execution_contract' in source
    assert 'AEFCNativeAttackHarness' in builder
    assert 'IEEE39BusSystem_AEFCUnpriv' in builder
    cfg=json.loads(CONFIG.read_text())
    assert cfg['native_contract']['full_state_mapping_available'] is False
    assert cfg['native_contract']['independently_validated_error_coverage'] is False
    assert cfg['native_contract']['required_full_state_certificate']
    assert cfg['native_contract']['surrogate_only']
    assert cfg['attack_end_step'] < cfg['stop_time']/cfg['sample_time']
    return dict(online_privilege_leaks=hits, native_safety_scope='four measured speeds, NO complete state coverage',
                full_state_certified=False, mode='static source and metadata inspection')

def dynamic_audit(directory:Path):
    manifest=json.loads((directory/'manifest.json').read_text())
    rows=list(csv.DictReader((directory/'summary.csv').open()))
    cfg=json.loads(CONFIG.read_text())
    assert manifest['full_state_certified'] is False
    assert manifest['rows']==len(rows)>0
    assert len({(r['seed'],r['method'],r['scenario'],r['attack_scale']) for r in rows})==len(rows)
    assert all(r['full_state_certified_count']=='0' for r in rows)
    sampled_count=0;exposed_count=0;restored=0;unsafe_proxy=0;status_negative=0
    findings=[];by_method={}
    for row in rows:
        scale=float(row['attack_scale']);seed=int(row['seed']);sc=row['scenario'];met=row['method']
        fp=directory/f'scale_{scale:g}'/sc/met/f'seed_{seed:02d}.jsonl'
        assert fp.exists(),fp
        trace=[json.loads(line) for line in fp.read_text().splitlines()]
        assert len(trace)==int(round(cfg['stop_time']/cfg['sample_time']))+1
        assert all(record['seed']==seed and record['method']==met and
                   record['scenario']==sc for record in trace)
        assert all(record['full_state_certified'] is False and
                   record['full_state_coverage'] is False for record in trace)
        sample_count=len(trace);sampled_count+=sample_count
        for i,r in enumerate(trace):
            assert len(r['native_speed'])==len(r['speed_normalized'])==4
            assert len(r['shield_action'])==len(r['post_shield_attack'])==4
            assert r['surrogate_released']==(r['proxy_status']>0)
            assert r['surrogate_released']==(r['proxy_status'] in (1,2,3,4))
            assert max(abs(x) for x in r['post_shield_attack']) <= cfg['native_contract']['post_shield_attack_upper']+1e-9
            max_speed=max(abs(x) for x in r['speed_normalized'])
            assert r['sampled_speed_inside_proxy'] == (max_speed<=cfg['normalized_safe_limit']+1e-9)
            if not r['sampled_speed_inside_proxy']:unsafe_proxy+=1
            status_negative+=int(r['proxy_status']<0)
        idx=cfg['attack_end_step']
        threshold=cfg['normalized_recovery_limit']
        exposed=max(abs(z) for z in trace[idx]['speed_normalized']) > threshold
        first=None
        if exposed:
            for k in range(idx+1,len(trace)-19):
                if all(max(abs(z) for z in trace[j]['speed_normalized'])<=threshold
                       for j in range(k,k+20)):
                    first=k;break
        corrected=first is not None
        assert (row['exposed_at_attack_stop']=='1')==exposed
        assert (row['strict_recovered']=='1')==corrected
        if corrected:
            assert abs(float(row['time_from_attack_stop'])-(trace[first]['time']-trace[idx]['time']))<=1e-7
        exposed_count+=int(exposed);restored+=int(corrected)
        by_method.setdefault(met,dict(episodes=0,exposed=0,recovered=0,surrogate_proxy_releases=0))
        by_method[met]['episodes']+=1
        by_method[met]['exposed']+=int(exposed)
        by_method[met]['recovered']+=int(corrected)
        by_method[met]['surrogate_proxy_releases']+=sum(int(x['surrogate_released']) for x in trace)
    audit=dict(state='PASS_WITH_INCOMPLETE_FULL_STATE_CERTIFICATION',episodes=len(rows),
               samples=sampled_count,exposed=exposed_count,recovered=restored,
               speed_proxy_violations=unsafe_proxy,proxy_rejections=status_negative,
               by_method=by_method,findings=findings,
               important='No complete IEEE39 state, no certified nonlinear reachability, no formal full-state safety or recovery claim')
    (directory/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))
    return audit

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--results',type=Path,default=None)
    x=p.parse_args()
    print(json.dumps(static_audit(),indent=2))
    if x.results: dynamic_audit(x.results)
