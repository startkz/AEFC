#!/usr/bin/env python3
"""Evidence-first TDSC-R1 IEEE39 complete physical safety promotion decision.

Requires real original immutable Matlab traces, real 59-predicate physical
sensor matrix, and genuinely unseen seed one-step observed enclosure.
Never upgrades output-surrogate safety to whole-network certification.
"""
import argparse
import json
from pathlib import Path


def judge(forensic_file,sensor_matrix,one_step,out_file):
    F=json.loads(forensic_file.read_text())
    M=json.loads(sensor_matrix.read_text())
    E=json.loads(one_step.read_text())
    assert F["original_experiment_commit"]==E["source_commit"]
    groups=[F["smoke"],F["strict"],F["sixmethod"]]
    physical_episodes=sum(g["episodes"] for g in groups)
    physical_samples=sum(g["samples"] for g in groups)
    attack_samples=sum(g["attack_active_samples"] for g in groups)
    eligible=sum(g["alarm_cases"] for g in groups)
    restored=sum(g["completed_hold_20_recovery_cases"] for g in groups)
    ten_speed_viol=sum(g["all_ten_speed_envelope_violations"] for g in groups)
    assert physical_episodes==48 and physical_samples==8688
    assert attack_samples==3600 and eligible==0 and restored==0
    assert F["strict"]["refused_additional_pref_samples"]==1448
    assert F["matched_strict_4_pairs_identical_10_generator_physical_trajectories"]==4
    assert len(M["individual_safety_predicates"])==59
    assert M["counts"]["generator_speed_current_online_accepted"]==4
    assert M["counts"]["bus_voltage_channels_mapped"]==0
    assert len(E["overall"])==3
    obs25=next(x for x in E["overall"] if x["inflation_factor"]==1.25)
    assert obs25["violations"]>0
    blocks=[
        "NO_39_BUS_VOLTAGE_TRUSTED_ONLINE_MONITOR",
        "NO_COMPLETE_TEN_ROTOR_ANGLE_AND_BRANCH_THERMAL_MONITOR",
        "NO_PROVEN_SENSOR_INTEGRITY_OR_FULL_NETWORK_OBSERVER_ERROR_SET",
        "NO_ORIGINAL_SIMSCAPE_39BUS_NONLINEAR_INDEX1_DAE_INTERVAL_EXTENSION",
        "NO_PROVEN_UNIFORM_ALGEBRAIC_ROOT_AND_JACOBIAN_INTERVAL",
        "NO_NATIVE_FULL_STATE_ONE_STEP_AND_ENTIRE_HOLD_REACHABLE_TUBE",
        "NO_CERTIFIED_DEFAULT_GOVERNOR_EMERGENCY_VIABILITY_REGION",
        "NO_ATTACK_END_OUTSIDE_TO_HOLD20_GENUINE_PHYSICAL_RECOVERY_EVENT",
        "NO_INDEPENDENT_SEED_HELDOUT_PHYSICAL_RECOVERY_GAINS",
    ]
    result=dict(
        status="BLOCKED",
        full_native_ieee39_execution_safety_certified=False,
        reliable_post_attack_recovery_certified=False,
        six_method_recovery_superiority_established=False,
        original_native_commit=F["original_experiment_commit"],
        actual_simulink_physical_episodes=physical_episodes,
        original_physical_sample_points=physical_samples,
        actual_downstream_attack_samples=attack_samples,
        true_ten_generator_recovery_exposure_episodes=eligible,
        true_postattack_hold20_restoration_events=restored,
        observed_ten_generator_speed_envelope_breaches=ten_speed_viol,
        independent_strict_fail_closed_samples=F["strict"]["refused_additional_pref_samples"],
        four_matched_strict_default_governor_trajectories_identical=True,
        genuine_online_rotor_speed_channels=M["counts"]["generator_speed_current_online_accepted"],
        qualified_39_bus_voltage_channels=M["counts"]["bus_voltage_channels_mapped"],
        measured_one_step_speed_envelope_1p25x_violations=obs25["violations"],
        conditional_synthetic_DAE_krawczyk_picard_test_passed=True,
        synthetic_DAE_is_not_original_simscape_certificate=True,
        blocking_requirements=blocks,
        bounded_claim=(
            "Native MATLAB executed; observed ten-generator speeds and zero "
            "added Pref under strict rejection are reproducible sampled facts. "
            "No recovery event occurred. No physical 39-bus/branch/angle "
            "full-state or nonlinear DAE safety proof exists.")
    )
    out_file.parent.mkdir(parents=True,exist_ok=True)
    out_file.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--forensic",required=True,type=Path)
    p.add_argument("--sensors",required=True,type=Path)
    p.add_argument("--one-step",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    judge(args.forensic,args.sensors,args.one_step,args.output)
