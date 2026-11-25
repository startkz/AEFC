#!/usr/bin/env python3
"""Fail-open and oracle information audit for frozen historical code; read only.

Flags are explicit findings, not tests that should be modified to force PASS.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def audit(root=ROOT):
    native=(root/'experiments/matlab/AEFCNativeController.m').read_text()
    checkpoint=(root/'experiments/matlab/AEFCNativeCheckpointController.m').read_text()
    hydro=(root/'experiments/hydro_valve/run_hydro_valve_cps.py').read_text()
    findings=[
      dict(source='AEFCNativeController',id='NATIVE-ORACLE-RISK',
           observed=('beliefDist=norm(beliefNow-obj.cleanBelief,2);' in native and
                     'uncertainty=min(1,beliefDist);' in native),
           implication='main-study online risk depends on experimental cleanBelief'),
      dict(source='AEFCNativeController',id='NATIVE-ATTACK-LABEL-ADMISSION',
           observed=('if provenance(j)' in native),
           implication='main-study PATBU weights use synthetic attacker labels'),
      dict(source='AEFCNativeController',id='NATIVE-SHIELD-APPROX',
           observed=('pinv(obj.Bn)' in native and 'for iter=1:3' in native),
           implication='sensitivity-based finite projection is not robust CBF/CLF certification'),
      dict(source='AEFCNativeCheckpointController',id='CHECKPOINT-RISK-NO-CLEAN',
           observed=('uncertainty=min(1,norm(obsReceived-beliefNow,2))' in checkpoint),
           implication='checkpoint branch risk uses observable discrepancy, unlike legacy main'),
      dict(source='hydro_valve/run_hydro_valve_cps.py',id='HYDRO-UNCERTIFIED-BACKUP',
           observed=('return backup,True,False,float(backup_margin)' in hydro and
                     'else: u_cmd=backup_cmd.copy()' in hydro),
           implication='historic SIL executes fallback after unsuccessful feasible certification'),
    ]
    return dict(base_files_untouched=True,source_audit='static exact-code patterns',findings=findings,
                note='No formal execution guarantees inferred from source text; do not rewrite frozen results')

if __name__=='__main__': print(json.dumps(audit(),indent=2))
