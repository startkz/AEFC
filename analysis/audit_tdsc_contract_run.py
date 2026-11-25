#!/usr/bin/env python3
"""Strict, independent recomputation of every new hydraulic contract trace."""
import argparse
import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
from experiments.hydro_valve.run_hydro_valve_cps import Config, predict_next, safe_state
from experiments.hydro_valve.run_tdsc_contract_chain import (
    state_uncertainty, interval_step, in_recovery,
)

def audit(path: Path):
    m=json.loads((path/'manifest.json').read_text())
    summary=list(csv.DictReader((path/'summary.csv').open()))
    c=replace(Config(),steps=m['steps'],qin_uncertainty=.008,load_uncertainty=.020)
    expected={(sc,sd) for sc in m['scenarios']
              for sd in range(m['seed_start'],m['seed_start']+m['seeds'])}
    assert {(r['scenario'],int(r['seed'])) for r in summary}==expected
    assert len(summary)==len(expected)==len(m['results'])
    issue=[]; sample_count=0; certified=0; stopped=0; corrected=0; exposed=0
    summary_by_key={(r['scenario'],int(r['seed'])):r for r in summary}
    for sc,seed in sorted(expected):
        fp=path/f'seed_{seed}_{sc}.jsonl'
        assert hashlib.sha256(fp.read_bytes()).hexdigest()==m['file_sha256'][fp.name]
        trace=[json.loads(line) for line in fp.read_text().splitlines()]
        record=summary_by_key[(sc,seed)]
        assert len(trace)==int(record['steps'])
        assert all(row['t']==i for i,row in enumerate(trace))
        sample_count+=len(trace)
        for i,row in enumerate(trace):
            before=np.asarray(row['state_before']); sensor=np.asarray(row['local_plc_norm'])
            lo,hi=state_uncertainty(sensor,c)
            covered=bool(np.all(before>=lo-1e-12) and np.all(before<=hi+1e-12))
            assert covered==row['coverage'],(sc,seed,i,'observer coverage mismatch')
            if not covered: issue.append((sc,seed,i,'COVERAGE_FAILURE'))
            if row['command_released']:
                certified+=1
                assert row['status'].startswith('CERTIFIED_')
                assert row['margin'] is not None and row['margin']>=-1e-12
                u=np.asarray(row['command']); post=np.asarray(row['post_attack'])
                assert np.max(np.abs(post))<=c.command_attack_bound+1e-12
                assert np.all(u>=c.command_attack_bound-1e-12)
                assert np.all(u<=1-c.command_attack_bound+1e-12)
                assert abs(row['qin']-c.qin_nominal)<=c.qin_uncertainty+1e-12 or not row['exogenous_covered']
                assert abs(row['load']-c.load_nominal)<=c.load_uncertainty+1e-12 or not row['exogenous_covered']
                actual=np.asarray(row['state_true'])
                pred=predict_next(before,u,row['qin'],row['load'],c,post)
                assert np.max(np.abs(pred-actual))<=1e-11,(sc,seed,i,'plant mismatch')
                step_lo,step_hi=interval_step(lo,hi,u,c)
                if np.any(actual<step_lo-1e-11) or np.any(actual>step_hi+1e-11):
                    issue.append((sc,seed,i,'INTERVAL_MISSED_TRUE_NEXT'))
                expected_safe=bool(safe_state(actual,c))
                assert row['safe']==expected_safe,(sc,seed,i,'safe predicate mismatch')
                if not expected_safe: issue.append((sc,seed,i,'STATE_SAFETY_VIOLATION'))
                if not row['exogenous_covered']:issue.append((sc,seed,i,'EXOGENOUS_NOT_COVERED'))
                actual_rec=in_recovery(actual,c,m['recovery_flow_tolerance'],m['recovery_speed_tolerance'])
            else:
                stopped+=1
                assert i==len(trace)-1 and not row['status'].startswith('CERTIFIED_')
                actual_rec=in_recovery(before,c,m['recovery_flow_tolerance'],m['recovery_speed_tolerance'])
            assert actual_rec==row['recovery'],(sc,seed,i,'recovery predicate mismatch')
        at_stop=next((r for r in trace if r['t']==m['attack_step_end']),None)
        is_exposed=bool(at_stop and not at_stop['recovery'])
        exposed+=int(is_exposed)
        assert is_exposed==(record['initial_outside_recovery']=='True'),(sc,seed,'exposure mismatch')
        first=None; hold=m['consecutive_recovery_samples']; end=m['attack_step_end']
        if is_exposed and not record['failure']:
            for j in range(end+1,len(trace)-hold+1):
                if all(trace[k]['recovery'] for k in range(j,j+hold)):
                    first=j;break
        corrected+=int(first is not None)
        assert (first is not None)==(record['corrected']=='True'),(sc,seed,'corrected mismatch')
        assert (record['first_recovery_step']=='' if first is None else int(record['first_recovery_step'])==first)
    result=dict(status='PASS' if not issue else 'ASSUMPTION_OR_PHYSICAL_FAILURE',
                episodes=len(expected),sample_count=sample_count,certified_commands=certified,
                explicit_contract_failures=stopped,exposed_at_attack_end=exposed,
                corrected_20_samples=corrected,findings=issue[:100],finding_count=len(issue),
                interpretation='Discrete plant coverage and transcript consistency, NOT continuous-time CBF, neural FRL or hardware certification')
    (path/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if issue: raise RuntimeError('Trace failure: '+str(issue[:10]))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True)
    audit(Path(p.parse_args().input))
