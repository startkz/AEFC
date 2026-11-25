#!/usr/bin/env python3
"""Non-negotiable full IEEE39 safety/causal-results promotion gate.

All source data are *actual repo* files or an independently downloaded
CI inventory. This gate deliberately reports BLOCKED until sound complete
state estimation, nonlinear/DAE reachable tubes, emergency governor control,
and matched physical exposure/holdout evidence can be audited. It never
interprets "CI succeeded" as "physical safety certified".
"""
import argparse
import hashlib
import json
from pathlib import Path

def inspect(registry:Path,mapping:Path,inventory:Path|None=None,comparison:Path|None=None):
    spec=json.loads(registry.read_text())
    mp=json.loads(mapping.read_text())
    blockers=[]
    evidence={}
    nobs=len(mp['observation_edges'])
    nctrl=len(mp['control_edges'])
    evidence.update(
        mapped_native_sensors=nobs,
        mapped_native_control_ports=nctrl,
        causal_pref_mapping_verified=bool(mp.get('validated',False)),
        mapping_scope=mp.get('selection_policy'))
    if nobs==0:blockers.append('NO_ONLINE_PHYSICAL_MEASUREMENTS')
    if not mp.get('validated',False):blockers.append('CAUSAL_MAPPING_NOT_VERIFIED')
    if inventory and inventory.exists():
        inv=json.loads(inventory.read_text())
        evidence['logged_offline_state_entries']=inv.get('n_state_entries')
        evidence['logged_dynamic_state_components_estimate']=inv.get('n_scalar_dynamic_components_estimate')
        evidence['all_generator_speed_paths_located']=inv.get('all_generator_speed_channels_located')
        evidence['offline_state_log_available']=inv.get('state_output_nonempty')
        evidence['offline_state_log_is_trusted_online_measurement']=False
        if not inv.get('state_output_nonempty'):blockers.append('NATIVE_FULLSTATE_LOG_NOT_AVAILABLE')
    else:
        blockers.append('NO_INDEPENDENT_NATIVE_STATE_INVENTORY')
    ob=spec['online_state_estimator']
    if not ob.get('coverage_verified',False):
        blockers.append('NO_FULLSTATE_ONLINE_OBSERVER_COVERAGE_PROOF')
    if not ob.get('error_bound_proof'):
        blockers.append('NO_OBSERVER_ERROR_BOUND_PROOF')
    if not ob.get('source_measurement_map'):
        blockers.append('NO_ALL_STATE_MEASUREMENT_MAP')
    for p in spec['required_predicates']:
        if p.get('status')!='verified' or not p.get('bounds_source'):
            blockers.append('UNVERIFIED_PHYSICAL_PREDICATE:'+p['name'])
    tube=spec['sampled_reachable_tube']
    if not tube.get('validated',False):
        blockers.append('NO_VALIDATED_FULL_NETWORK_SAMPLED_REACHABLE_TUBE')
    if not tube.get('guaranteed_model_residual_bound'):
        blockers.append('NO_FORMAL_DISCRETE_MODEL_RESIDUAL_ENVELOPE')
    hold=spec['intersample_reachable_tube']
    if not hold.get('validated',False) or not hold.get('nonlinear_and_algebraic_constraints_covered',False):
        blockers.append('NO_FULL_NONLINEAR_INTERSAMPLE_REACHABILITY')
    backup=spec['backup']
    for k in ('emergency_actuator_authority_verified','fallback_reachable_set_feasible',
              'deadline_and_solver_timeout_verified','original_governors_independently_certified'):
        if not backup.get(k,False):blockers.append('UNCERTIFIED_EMERGENCY_CONTROL:'+k)
    original=spec.get('verified_native_mat_file')
    originalsha=spec.get('verified_native_mat_sha256')
    if not original or not originalsha:
        blockers.append('NO_HASH_PINNED_NATIVE_FULLSTATE_MODEL_ARTIFACT')
    else:
        fp=registry.parent.parent/str(original)
        if not fp.is_file() or hashlib.sha256(fp.read_bytes()).hexdigest()!=originalsha:
            blockers.append('UNVERIFIED_NATIVE_ARTIFACT_SHA256')
    if not comparison or not comparison.exists():
        blockers.append('NO_INDEPENDENT_SIX_METHOD_RECOVERY_HOLDOUT')
    else:
        cm=json.loads(comparison.read_text())
        evidence['six_method_comparison_rows']=len(cm.get('results',[]))
        if len(cm.get('results',[]))<6:
            blockers.append('INSUFFICIENT_SIX_METHOD_PAIRED_CELLS')
        if not cm.get('all_attacked_scenarios_physically_exposed',False):
            blockers.append('NO_CONFIRMED_ATTACK_END_PHYSICAL_EXPOSURE')
        if not cm.get('complete_native_safety_certified',False):
            blockers.append('PAIRED_COMPARISON_STILL_PROXY_ONLY')
    ready=len(blockers)==0
    claim=spec['manuscript_promotion_gate']
    if claim.get('full_state_execution_safety_certified',False) and not ready:
        raise AssertionError('Premature IEEE39 complete safety claim while material blockers exist')
    if claim.get('accepted_real_ieee39_recovery_paired_holdout',False) and (
         not comparison or not comparison.exists()):
        raise AssertionError('Premature native physical recovery claim without full holdout')
    report={'status':'READY_FOR_INDEPENDENT_PROOF_REVIEW' if ready else 'BLOCKED',
            'full_network_certified':False if not ready else None,
            'evidence':evidence,'blocking_requirements':blockers,
            'interpretation':'Observed 4-speed surrogate or synthetic solver cannot close complete IEEE39 certification'}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--registry',type=Path,default=Path('configs/ieee39_fullstate_certification_requirements.json'))
    a.add_argument('--mapping',type=Path,default=Path('results/ieee39_r2024b/interface_mapping.json'))
    a.add_argument('--inventory',type=Path)
    a.add_argument('--comparison',type=Path)
    args=a.parse_args()
    inspect(args.registry,args.mapping,args.inventory,args.comparison)
