#!/usr/bin/env python3
"""Audit the preregistered 10-seed IEEE39 Bus16 strict confirmatory replay.

The audit distinguishes reproducibility from independent physical sampling:
the frozen experiment contains no seed-driven disturbance in the native plant.
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/ieee39_fault_recovery_r1/confirmatory_v1"
PROTOCOL = ROOT / "configs/ieee39_native_fault_recovery_protocol_r1.json"
METHODS = ("AEFC-Full", "Supervisor-only")
SEEDS = tuple(range(80, 90))
PHYSICAL_KEYS = (
    "time",
    "bus_vt_sections",
    "bus16_voltage_sections",
    "faulted_bus16_1_voltage",
    "adjacent_B16_B17_current_A",
    "all_ten_generator_speed",
    "all_ten_speed_normalized",
    "original_governor_pref",
    "delivered_pref",
    "fault_active_window",
    "recovery_set_satisfied",
)

def flatten(x):
    if isinstance(x, list):
        for v in x:
            yield from flatten(v)
    elif isinstance(x, bool):
        yield float(x)
    else:
        yield float(x)

def maxdiff(a, b):
    aa, bb = list(flatten(a)), list(flatten(b))
    assert len(aa) == len(bb), (len(aa), len(bb))
    return max((abs(x-y) for x, y in zip(aa, bb)), default=0.0)

def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def compare_trace(a, b, keys):
    assert len(a) == len(b)
    return {key: max(maxdiff(x[key], y[key]) for x, y in zip(a, b)) for key in keys}

def main():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    expected_fault = protocol["fault_parameters_frozen"]
    assert protocol["confirmatory_seeds"] == list(SEEDS)
    assert protocol["methods"] == list(METHODS)
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    gate = json.loads((OUT / "strict_refusal_gate.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((OUT / "summary.csv").open(encoding="utf-8")))
    assert len(rows) == 20, len(rows)
    assert set(int(r["seed"]) for r in rows) == set(SEEDS)
    assert set(r["method"] for r in rows) == set(METHODS)
    assert gate["passed"] is True, gate
    assert gate["confirmatory_experiment_started"] is True
    assert gate["pilot_exposure_gate_passed"] is True
    assert gate["pilot_source_run_id"] == 45920175235
    assert gate["thresholds_changed"] is False
    assert gate["fault_parameters_changed"] is False
    assert manifest["execution_mode"] == "strict_fail_closed"
    assert manifest["physical_seed_randomization"] is False
    assert manifest["full_network_safety_certified"] is False
    assert manifest["independent_governor_viability_certified"] is False

    row_index = {(r["method"], int(r["seed"])): r for r in rows}
    for seed in SEEDS:
        a = row_index[("AEFC-Full", seed)]
        b = row_index[("Supervisor-only", seed)]
        for r in (a, b):
            assert int(r["fault_start_s"]) == int(expected_fault["fault_start_time_s"])
            assert math.isclose(float(r["fault_duration_s"]), expected_fault["fault_duration_s"], abs_tol=1e-12)
            assert int(r["bus_logical_ids"]) == 39
            assert int(r["bus_physical_sections"]) == 41
            assert int(r["branch_current_series"]) == 126
            assert int(r["generator_speed_channels"]) == 10
            assert float(r["max_added_pref_correction"]) < 1e-12
            assert float(r["max_pref_interposition_residual"]) < 1e-6
            assert int(r["execution_released_samples"]) == 0
            assert int(r["backup_action_used_samples"]) == 0
            assert int(r["full_state_certified_samples"]) == 0
            assert int(r["proxy_contract_pass_samples"]) == 0
            assert int(r["exposed_during_fault"]) == 1
            assert int(r["recovered_after_fault"]) == 1
            assert int(r["right_censored"]) == 0
            assert math.isclose(float(r["recovery_time_s"]), 2.08333333333333, abs_tol=1e-10)
        assert float(a["max_added_pref_correction"]) == float(b["max_added_pref_correction"]) == 0.0

    within_pair = {}
    cross_seed = {}
    branch_cross_seed = {}
    for method in METHODS:
        traces = {}
        branch_summaries = {}
        fault_summaries = {}
        bus_maps = {}
        for seed in SEEDS:
            folder = OUT / method
            traces[seed] = load_jsonl(folder / f"seed_{seed:02d}.jsonl")
            assert len(traces[seed]) == 481, (method, seed, len(traces[seed]))
            branch_summaries[seed] = json.loads((folder / f"seed_{seed:02d}.branch-current.json").read_text())
            fault_summaries[seed] = json.loads((folder / f"seed_{seed:02d}.fault-current.json").read_text())
            bus_maps[seed] = json.loads((folder / f"seed_{seed:02d}.bus-map.json").read_text())
            assert len(branch_summaries[seed]) == 126
            assert len(bus_maps[seed]) == 41
            assert len({x["logical_bus"] for x in bus_maps[seed]}) == 39
            assert len(fault_summaries[seed]) >= 1
            for x in traces[seed]:
                assert x["execution_released"] is False
                assert x["backup_action_used"] is False
                assert x["full_state_certified"] is False
                assert x["proxy_contract_pass"] is False
                assert maxdiff(x["original_governor_pref"], x["delivered_pref"]) <= 1e-12
        # Within each seed, AEFC-Full and Supervisor-only must have the same
        # plant trajectory because strict fail-closed execution releases zero.
        for seed in SEEDS:
            a = traces[seed]
            b = load_jsonl(OUT / "Supervisor-only" / f"seed_{seed:02d}.jsonl") if method == "AEFC-Full" else traces[seed]
            if method == "AEFC-Full":
                within_pair[str(seed)] = compare_trace(a, b, PHYSICAL_KEYS)
        # Across seed values, physical traces should be checked rather than
        # presumed independent. The native fault model is deterministic.
        ref_seed = SEEDS[0]
        for seed in SEEDS[1:]:
            d = compare_trace(traces[ref_seed], traces[seed], PHYSICAL_KEYS)
            cross_seed[f"{method}:{ref_seed}:{seed}"] = d
            branch_cross_seed[f"{method}:{ref_seed}:{seed}"] = {
                "branch_current_summary_maxdiff": maxdiff(branch_summaries[ref_seed], branch_summaries[seed]),
                "fault_current_summary_maxdiff": maxdiff(fault_summaries[ref_seed], fault_summaries[seed]),
            }

    max_within = max(v for d in within_pair.values() for v in d.values())
    max_cross = max(v for d in cross_seed.values() for v in d.values())
    max_branch = max(v for d in branch_cross_seed.values() for v in d.values())
    assert max_within <= 1e-10, max_within
    assert max_cross <= 1e-10, max_cross
    assert max_branch <= 1e-10, max_branch

    report = {
        "status": "PASS_STRICT_CONFIRMATORY_REPLAY_REPRODUCIBILITY",
        "episodes": len(rows),
        "methods": list(METHODS),
        "seeds": list(SEEDS),
        "pilot_gate_run_id": 45920175235,
        "fault_parameters": expected_fault,
        "recovery_predicate": protocol["preregistered_recovery_predicate"],
        "all_20_episodes_exposed_and_recovered": True,
        "all_20_episodes_zero_added_pref_correction": True,
        "all_20_episodes_zero_execution_release": True,
        "all_20_episodes_zero_backup_action": True,
        "all_20_episodes_zero_full_state_certification": True,
        "physical_trajectory_method_pairing_max_abs_diff": max_within,
        "physical_trajectory_cross_seed_max_abs_diff": max_cross,
        "branch_and_fault_current_cross_seed_max_abs_diff": max_branch,
        "seed_driven_physical_perturbation": False,
        "inferential_independent_physical_seed_samples": False,
        "interpretation": (
            "The ten preregistered seed values reproduce the pilot's common Bus16 exposure, "
            "20-sample post-fault recovery predicate, and strict zero-release behavior. "
            "Native plant trajectories are identical across seed values because no seed-driven "
            "physical disturbance is present; this is a reproducibility confirmation, not "
            "ten independent physical samples and not an AEFC physical recovery-effect test."
        ),
        "full_network_safety_certified": False,
        "branch_thermal_limits_validated": False,
        "continuous_intersample_safety_certified": False,
        "backup_governor_viability_certified": False,
    }
    out = OUT / "confirmatory_reproducibility_audit.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
