#!/usr/bin/env python3
"""Create a reviewable *offline* IEEE39 state/measurement registry from original xout.

No solver states are silently promoted to physical state variables or
authenticated online observations. This is discovery, not certification.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

def build(original: Path, output: Path):
    raw=original.read_bytes()
    data=json.loads(raw)
    candidates=data.get('physical_rotor_speed_sensor_candidates',[])
    known={c['generator']:c['block'] for c in candidates}
    assert len(known)==10 and all(c['port']>=1 for c in candidates)
    entries=[]
    per_gen=defaultdict(lambda:dict(avr=0,governor=0,other=0))
    for x in data['state_entries']:
        block=x['blockpath']
        generator_match=re.search(r'Generators/(Gen\d+@Bus\d+)',block)
        generator=generator_match.group(1) if generator_match else None
        n=int(x['n_signal_components'])
        if generator and '/AVR and Exciter/' in block:
            category='generator_avr_controller_state';per_gen[generator]['avr']+=n
        elif generator and '/Governor and' in block:
            category='generator_governor_controller_state';per_gen[generator]['governor']+=n
        elif '/Grid/Solver Configuration/' in block:
            category='solver_internal_xout_not_verified_as_physical_state'
        else:
            category='unclassified_state_log';per_gen[generator or 'other']['other']+=n
        entries.append(dict(
            index=x['index'],simulink_blockpath=block,simulink_logged_name=x['name'],
            generator=generator,source_category=category,logged_scalar_components=n,
            qualified_as_independent_physical_state=False,
            certified_online_observation=False,
            verified_error_bound=None,
            verified_dynamics_map=None,
            invariant_state_constraints=None))
    tot=sum(e['logged_scalar_components'] for e in entries)
    assert len(entries)==int(data['n_state_entries'])
    assert tot==int(data['n_scalar_dynamic_components_estimate'])
    out=dict(
        source='actual original MATLAB R2024b IEEE39BusSystem xout (OFFLINE)',
        source_sha256=hashlib.sha256(raw).hexdigest(),
        log_entries=len(entries),log_scalar_values=tot,
        actual_independent_physical_state_dimension=None,
        physical_complete_DAE_state_verified=False,
        physical_complete_online_observer_verified=False,
        sensor_integrity_proven=False,
        data_scope='mapping discovery only',
        generators=dict(sorted(per_gen.items())),
        genuine_existing_generator_speed_signal_paths=known,
        dynamic_state_log_entries=entries,
        certification_blockers=[
            'SAVED_XOUT_INCLUDES_SOLVER_INTERNAL_VALUES',
            'NO_HONEST_FULL_NETWORK_ONLINE_MEASUREMENT_COVERAGE',
            'NO_DAE_DIFFERENTIAL_ALGEBRAIC_DECOMPOSITION',
            'NO_SAFE_REGIONS_FOR_GENERATOR_INTERNAL_STATES_AND_NETWORK_CONSTRAINTS',
            'NO_GLOBAL_CONSERVATIVE_REACHABILITY_BOUND',
            'NO_PROVEN_INTERSAMPLE_TUBE_AND_EMERGENCY_BACKUP',
        ],
    )
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in (
        'source_sha256','log_entries','log_scalar_values',
        'actual_independent_physical_state_dimension',
        'physical_complete_DAE_state_verified',
        'physical_complete_online_observer_verified','generators',
    )},indent=2,ensure_ascii=False))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    build(args.input,args.output)
