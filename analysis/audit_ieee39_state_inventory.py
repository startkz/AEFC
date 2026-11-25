#!/usr/bin/env python3
"""Independent report of native IEEE39 offline dynamics vs trusted sensor coverage."""
import argparse
import json
from pathlib import Path

def audit(path: Path):
    info=json.loads(path.read_text(encoding='utf8'))
    assert info['source']=='MathWorks R2024b IEEE39BusSystem original Simulink simulation'
    assert info['full_state_observability_verified'] is False
    assert info['model_reachability_verified'] is False
    assert info['full_state_safety_certificate'] is False
    total=info.get('n_scalar_dynamic_components_estimate',0)
    n_entries=info.get('n_state_entries',0)
    assert total>=0 and n_entries>=0
    groups={
        'generator_avr_exciter':{'entries':0,'scalar_values':0},
        'generator_governor':{'entries':0,'scalar_values':0},
        'grid_solver_internal':{'entries':0,'scalar_values':0},
        'other_logged_items':{'entries':0,'scalar_values':0},
    }
    entries=info.get('state_entries',[])
    for entry in entries:
        path=entry.get('blockpath','')
        if '/Generators/' in path and '/AVR and Exciter/' in path:
            group='generator_avr_exciter'
        elif '/Generators/' in path and '/Governor and' in path:
            group='generator_governor'
        elif '/Grid/Solver Configuration/' in path:
            group='grid_solver_internal'
        else:
            group='other_logged_items'
        groups[group]['entries']+=1
        groups[group]['scalar_values']+=int(entry.get('n_signal_components',0))
    assert sum(x['entries'] for x in groups.values())==n_entries
    assert sum(x['scalar_values'] for x in groups.values())==total
    grid_largest=max((int(x.get('n_signal_components',0))
                      for x in entries if '/Grid/Solver Configuration/' in x.get('blockpath','')),default=0)
    evidence=dict(
        audit_status=info['audit_status'],
        logged_dynamic_state_entries=n_entries,
        estimated_logged_scalar_components=total,
        logged_entries_by_source=groups,
        largest_grid_solver_internal_vector_components=grid_largest,
        estimated_independent_physical_dynamic_state_dimensions=None,
        reason='Saved solver-internal states/inputs cannot automatically be counted as physical differential states',
        trusted_online_rotor_speed_sensors=info['sensor_count_online'],
        observed_speed_mapping_per_state_inventoried=False,
        complete_network_observability_proven=False,
        rigorous_plant_uncertainty_bound_available=False,
        real_native_full_state_certificate=False,
        limitation=(
            'Offline Simulink xout is not an authenticated online measurement. '
            'A count of logged states is not a proof of observability; DAEs/algebraic bus '
            'variables may not appear in xout. This audit cannot authorize safety claims.'
        ),
    )
    print(json.dumps(evidence,indent=2,ensure_ascii=False))
    return evidence

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('inventory',type=Path)
    args=p.parse_args()
    audit(args.inventory)
