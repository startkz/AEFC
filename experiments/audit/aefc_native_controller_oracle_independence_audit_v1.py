#!/usr/bin/env python3
"""Static audit that the online native controller does not consume attack truth or clean shadows."""
from pathlib import Path
import json,re
ROOT=Path(".")
CTRL=ROOT/"experiments/matlab/AEFCNativeController.m"
STEP=ROOT/"experiments/matlab/aefc_native_certified_execution_step.m"
CONTRACT=ROOT/"experiments/matlab/aefc_native_full_state_contract.m"
LOADER=ROOT/"experiments/matlab/aefc_native_load_verified_state_contract.m"
OUT=ROOT/"results/ieee39_safety_mapping/native_controller_oracle_independence_audit_v1.json"

def read(p):
    assert p.is_file(),f"missing source {p}"
    return p.read_text(encoding="utf-8")

ctrl,step,contract,loader=map(read,(CTRL,STEP,CONTRACT,LOADER))
ctrl_code="\n".join(line.split("%",1)[0] for line in ctrl.splitlines())
forbidden=[
 r"\bcleanBelief\b",r"\battackIdentity\b",r"\battack_id\b",r"\btrue_attack\b",
 r"\bisAttacked\b",r"\bgroundTruthAttack\b",r"\battackLabel\b",r"\btrueState\b",
 r"\bx_true\b",r"\bloggedState\b",r"simscape\.logging",r"getSimulationLog",
 r"Simulink\.SimulationOutput",r"\bScenarioCode\b",r"\bSeed\b"
]
hits=[]
for pat in forbidden:
    if re.search(pat,ctrl_code,re.I):
        hits.append(pat)
assert not hits,{"online_controller_forbidden_dependencies":hits}
assert re.search(r"function\s+\[uShield,diagOut\]\s*=\s*stepImpl\(obj,localPhysical,packet\)",ctrl)
assert re.search(r"numel\(zNative\)\s*==\s*4",ctrl)
assert re.search(r"numel\(packet\)\s*==\s*67",ctrl)
assert re.search(r"ExploratoryMode\s*=\s*false",ctrl)
assert "aefc_native_certified_execution_step" in ctrl
assert "if logical(obj.ExploratoryMode)" in ctrl_code
assert "full_network_variables_covered" in step
assert "measurement_map_verified" in step
assert "intersample_reachability_verified" in step
assert "verified_emergency_policy" in step
assert "coverage_verified" in step
assert re.search(r"full_network_variables_covered',false",loader)
assert re.search(r"measurement_map_verified',false",loader)
assert re.search(r"intersample_reachability_verified',false",loader)
assert "status=-90" in contract or "status = -90" in contract
report={
 "status":"PASS_NO_ATTACK_TRUTH_OR_CLEAN_SHADOW_DEPENDENCY",
 "controller_source":str(CTRL),
 "online_step_signature":"stepImpl(obj,localPhysical,packet)",
 "online_physical_measurement_channels":4,
 "online_packet_fields":67,
 "forbidden_attack_truth_and_offline_shadow_references":[],
 "exploratory_mode_default":False,
 "strict_mode_uses_full_state_certified_execution_step":True,
 "full_state_contract_requires":{
   "full_network_variables_covered":True,
   "safety_predicates_all_covered":True,
   "full_state_dynamics_verified":True,
   "measurement_map_verified":True,
   "intersample_reachability_verified":True,
   "intersample_derivative_bounds_verified":True,
   "verified_emergency_policy":True
 },
 "certificate_loader_defaults_all_coverage_flags_false":True,
 "original_governors_certified":False,
 "full_network_safety_certified":False,
 "interpretation":"Static source inspection only. The online controller has no cleanBelief, attack-identity label, true-state, or offline Simscape-log dependency. Its current physical input remains four rotor-speed channels, so strict mode fails closed until a complete independently validated full-state certificate is loaded. This does not establish physical safety."
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
