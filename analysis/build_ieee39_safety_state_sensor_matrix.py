#!/usr/bin/env python3
"""Evidence-backed IEEE39 required safety state -> actual online sensors matrix.

Input registry from original R2024b 201-entry native state xout, structural
census of 9102 actual blocks, and validated FOUR rotor speed/Pref mapping.
Unmeasured bus/branch variables are NEVER fabricated or granted a sensor.
"""
import argparse
import json
import re
from pathlib import Path


def run(census,registry,mapping,out):
    c=json.loads(census.read_text())
    r=json.loads(registry.read_text())
    m=json.loads(mapping.read_text())
    assert c["scanned_blocks"]==9102
    assert len(r["genuine_existing_generator_speed_signal_paths"])==10
    assert m["validated"] and len(m["observation_edges"])==4
    trusted_assumption=set(m["observation_generator_keys"])
    known=r["genuine_existing_generator_speed_signal_paths"]
    assert len(trusted_assumption)==4
    requirements=[]
    for key,path in sorted(known.items()):
        requirements.append(dict(predicate=f"generator_angular_speed:{key}",
            physical_system_component=key,safety_quantity="rotor_speed",
            native_physical_signal_path=path,
            existing_monitor_offline=True,
            current_online_controller_input=key in trusted_assumption,
            legal_local_sensor_is_assumption_only=key in trusted_assumption,
            independent_sensor_attestation_or_error_coverage_verified=False,
            full_state_dynamics_verified=False,
            mathematical_reachability_verified=False))
        requirements.append(dict(predicate=f"generator_rotor_angle:{key}",
            physical_system_component=key,safety_quantity="rotor_angle",
            native_physical_signal_path=None,
            existing_monitor_offline=False,
            current_online_controller_input=False,
            legal_local_sensor_is_assumption_only=False,
            independent_sensor_attestation_or_error_coverage_verified=False,
            full_state_dynamics_verified=False,
            mathematical_reachability_verified=False))
    for i in range(1,40):
        requirements.append(dict(predicate=f"voltage_magnitude:bus_{i:02d}",
            physical_system_component=f"Bus {i}",
            safety_quantity="bus_voltage_magnitude",
            native_physical_signal_path=None,
            existing_monitor_offline=False,
            current_online_controller_input=False,
            legal_local_sensor_is_assumption_only=False,
            independent_sensor_attestation_or_error_coverage_verified=False,
            full_state_dynamics_verified=False,
            mathematical_reachability_verified=False))
    non_scalar_safety=[
        dict(predicate="every_branch_current_thermal_limit",
             physical_system_component="all line/transformer branches (exact native count not yet verified)",
             safety_quantity="branch_current",
             native_physical_signal_path=None,
             required_channel_count=None),
        dict(predicate="every_branch_active_reactive_power_flow",
             physical_system_component="all line/transformer branches (exact native count not yet verified)",
             safety_quantity="branch_power",
             native_physical_signal_path=None,
             required_channel_count=None),
        dict(predicate="generator_governor_exciter_internal_safety",
             physical_system_component="native generator AVR/Governor state and actuator limits",
             safety_quantity="state_estimator_and_actuator_saturation",
             native_physical_signal_path=None,
             required_channel_count=None),
    ]
    matrix=dict(source={
        "model":"original official MathWorks R2024b IEEE39BusSystem",
        "native_saved_state_entries":r["log_entries"],
        "native_saved_scalar_values":r["log_scalar_values"],
        "independent_physical_DAE_state_dimension_verified":False,
        "scanned_blocks":c["scanned_blocks"],
        "four_sensor_mapping_rule":m["selection_policy"],
        "offline_saved_state_source_sha256":r["source_sha256"],
    },
    counts=dict(generator_speed_monitored_offline=10,
                generator_speed_current_online_accepted=4,
                trusted_sensor_error_bounds_proven=0,
                generator_rotor_angles_mapped=0,
                bus_voltage_channels_required=39,
                bus_voltage_channels_mapped=0,
                branch_current_coverage_proven=False,
                branch_power_coverage_proven=False,
                internal_controller_states_saved_as_xout=180,
                independent_physical_state_count_verified=False),
    individual_safety_predicates=requirements,
    unresolved_branch_and_internal_predicates=non_scalar_safety,
    full_native_state_observation_complete=False,
    algebraic_network_reachability_verified=False,
    intersample_entire_cps_reachability_verified=False,
    verified_fallback_governor_viability=False,
    outcome="BLOCKED_INCOMPLETE_GENUINE_IEEE39_SENSOR_COVERAGE")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(matrix,indent=2,ensure_ascii=False)+"\n")
    assert len(requirements)==59
    print(json.dumps(matrix["counts"],indent=2))
    return matrix


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--census",type=Path,required=True)
    p.add_argument("--registry",type=Path,required=True)
    p.add_argument("--mapping",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    run(a.census,a.registry,a.mapping,a.output)
