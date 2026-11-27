#!/usr/bin/env python3
"""Audit completeness of the native IEEE39 Simscape Series metadata registry.

This is an OFFLINE signal-leaf inventory check. It deliberately does not
interpret the number of logged leaves as an independent state dimension.
"""
from __future__ import annotations
import collections
import json
import pathlib

source = pathlib.Path(
    "results/ieee39_safety_mapping/native_simscape_full_series_registry_v3.json"
)
if not source.is_file():
    raise SystemExit(f"missing registry: {source}")
data = json.loads(source.read_text(encoding="utf-8"))

registry = data.get("series_registry", [])
counts = data.get("series_category_counts", {})
expected = {
    "bus_voltage": 41,
    "line_phase_current": 102,
    "transformer_winding_current": 24,
    "rotor_angle_candidate": 20,
    "generator_terminal_voltage_candidate": 20,
    "other_series": 19148,
}
actual = collections.Counter(item.get("category") for item in registry)
paths = [item.get("path") for item in registry]

assert data.get("simscape_log_available") is True
assert data.get("truncated") is False
assert data.get("series_registry_truncated") is False
assert data.get("series_registry_capture_stop_time_s") == 0.05
assert data.get("series_registry_count") == len(registry)
assert data.get("series_leaves_included") == len(registry)
assert data.get("series_leaves_encountered") == (
    data.get("series_leaves_included") + data.get("series_leaves_excluded")
)
assert data.get("series_leaves_excluded") == 0, data.get("excluded_series")
assert len(paths) == len(set(paths)), "duplicate Simscape Series paths"
assert sum(counts.values()) == len(registry), (counts, len(registry))
assert dict(actual) == expected, {"actual": dict(actual), "expected": expected}
assert counts == expected, {"category_counts": counts, "expected": expected}

for item in registry:
    assert item.get("path") and item.get("unit") is not None, item
    assert item.get("samples", 0) >= 2, item
    assert item.get("time_end", -1) >= item.get("time_start", 0), item
    assert item.get("category") in expected, item
    assert item.get("value_shape"), item

assert data.get("online_controller_input_channels") == 4
assert data.get("trusted_online_sensor_integrity_verified") is False
assert data.get("sensor_error_bounds_verified") == 0
assert data.get("complete_DAE_state_observability_verified") is False
assert data.get("full_state_dimension_verified") is False
assert data.get("sampled_one_step_reachable_tube_verified") is False
assert data.get("continuous_intersample_tube_verified") is False
assert data.get("branch_thermal_limits_validated") is False
assert data.get("backup_governor_viability_verified") is False
assert data.get("full_network_safety_certified") is False

summary = {
    "status": "PASS_OFFLINE_SERIES_REGISTRY_COMPLETENESS",
    "model": data.get("model"),
    "capture_window_s": [0.0, data["series_registry_capture_stop_time_s"]],
    "series_leaves_encountered": data["series_leaves_encountered"],
    "series_leaves_included": data["series_leaves_included"],
    "series_leaves_excluded": data["series_leaves_excluded"],
    "unique_paths": len(set(paths)),
    "category_counts": dict(actual),
    "online_controller_input_channels": data["online_controller_input_channels"],
    "trusted_online_sensor_integrity_verified": False,
    "sensor_error_bounds_verified": 0,
    "complete_DAE_state_observability_verified": False,
    "full_state_dimension_verified": False,
    "sampled_one_step_reachable_tube_verified": False,
    "continuous_intersample_tube_verified": False,
    "branch_thermal_limits_validated": False,
    "backup_governor_viability_verified": False,
    "full_network_safety_certified": False,
    "interpretation": (
        "All valid finite Simscape Series leaves observed in the 0-0.05 s "
        "inventory run are enumerated. The registry includes auxiliary, "
        "duplicated and algebraic series and is not an independent state "
        "dimension or an online sensor certificate."
    ),
}
out = pathlib.Path(
    "results/ieee39_safety_mapping/full_series_registry_audit_v3.json"
)
out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
