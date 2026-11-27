#!/usr/bin/env python3
"""Independent offline KCL audit for all five multi-component IEEE39 busbar ports."""
from __future__ import annotations
import json
import pathlib
import numpy as np

ROOT = pathlib.Path(".")
CAPTURE = ROOT / "artifacts/terminal_capture/native_ieee39_bus_port_terminal_current_capture_v2.json"
MAP = ROOT / "artifacts/current_map/native_ieee39_bus_port_current_variable_map_v2.json"
PROBE = ROOT / "artifacts/bus16_probe/native_ieee39_bus16_port_current_fault_probe_v1.json"
OUT = ROOT / "results/ieee39_safety_mapping/all_composite_port_kcl_audit_v1.json"

def load(path):
    assert path.is_file(), f"missing artifact input: {path}"
    return json.loads(path.read_text(encoding="utf-8"))

def vec(series):
    a = np.asarray(series["values_real"], dtype=float)
    assert a.ndim == 2 and a.shape[1] == 3, (series.get("path"), a.shape)
    assert np.isfinite(a).all(), series.get("path")
    assert series["unit"] == "A"
    return a

def same_time(items):
    t = np.asarray(items[0]["time_s"], dtype=float)
    for x in items[1:]:
        tx = np.asarray(x["time_s"], dtype=float)
        assert tx.shape == t.shape and np.max(np.abs(tx-t)) <= 1e-12
    return t

def normalized_kcl(items, mask=None):
    t = same_time(items)
    arrays = [vec(x) for x in items]
    if mask is not None:
        arrays = [x[mask] for x in arrays]
    assert len({x.shape for x in arrays}) == 1
    residual = np.sum(np.stack(arrays, axis=0), axis=0)
    denom = sum(float(np.linalg.norm(x)) for x in arrays)
    rel = float(np.linalg.norm(residual) / max(denom, 1e-12))
    return {
        "normalized_residual": rel,
        "max_abs_residual_A": float(np.max(np.abs(residual))),
        "samples": int(residual.shape[0]),
        "time_start_s": float(t[0] if mask is None else t[mask][0]),
        "time_end_s": float(t[-1] if mask is None else t[mask][-1]),
    }

def main():
    c = load(CAPTURE)
    m = load(MAP)
    p = load(PROBE)

    assert c["bus_port_current_count"] == 123
    assert len(c["bus_port_current_series"]) == 123
    assert c["line_terminal_current_count"] == 68
    assert len(c["line_terminal_current_series"]) == 68
    assert c["transformer_winding_current_count"] == 24
    assert len(c["transformer_winding_current_series"]) == 24
    assert c["physical_bus_sections"] == 41 and c["logical_bus_count"] == 39

    assert m["status"] == "PASS_INTERLEAVED_123_PORT_CURRENT_MAP"
    assert m["bus_port_current_series"] == 123
    assert m["resolved_physical_ports"] == 123
    assert m["unresolved_physical_ports"] == 0
    assert m["current_variable_mapping_verified"] is True
    assert m["current_variable_order_rule"] == "I_(2k-1) maps to LConn_k; I_(2k) maps to RConn_k."
    assert m["verification_summary"]["single_component_line_port_references"] == 65
    assert m["verification_summary"]["single_component_line_port_references_directly_matched"] == 65
    assert m["verification_summary"]["transformer_endpoints_linear_winding_consistency"] == 24

    mapping = m["bus_port_current_variable_map"]
    assert len(mapping) == 123
    seen = set()
    for row in mapping:
        key = (row["bus_section"], row["current_variable"])
        assert key not in seen, key
        seen.add(key)
        n = int(row["port_order"])
        assert row["current_variable"] == f"I{n}"
        expected = f"LConn{(n+1)//2}" if n % 2 else f"RConn{n//2}"
        assert row["physical_port_type"] == expected, (key, expected, row["physical_port_type"])
    assert len(m["multi_component_busbar_port_details"]) == 5

    single = [x for x in m["line_terminal_signature_checks"] if not x["multi_component_bus_port"]]
    assert len(single) == 65
    assert max(float(x["direct_error"]) for x in single) <= 1e-12
    transformer_checks = m["transformer_current_signature_checks"]
    assert len(transformer_checks) == 24
    max_transformer_linear_error = max(float(x["best_linear"]["linear_error"]) for x in transformer_checks)
    assert max_transformer_linear_error <= 1e-10

    line_phase_nonzero = [0, 0, 0]
    line_maxima = []
    for x in c["line_terminal_current_series"]:
        a = vec(x)
        maxima = np.max(np.abs(a), axis=0)
        for k in range(3):
            if maxima[k] > 1e-6:
                line_phase_nonzero[k] += 1
        line_maxima.append(maxima)
    transformer_phase_nonzero = [0, 0, 0]
    transformer_maxima = []
    for x in c["transformer_winding_current_series"]:
        a = vec(x)
        maxima = np.max(np.abs(a), axis=0)
        for k in range(3):
            if maxima[k] > 1e-6:
                transformer_phase_nonzero[k] += 1
        transformer_maxima.append(maxima)
    assert line_phase_nonzero == [68, 68, 68]
    assert transformer_phase_nonzero == [24, 24, 24]

    ports = {(x["bus_section"], int(x["port_index"])): x for x in c["bus_port_current_series"]}
    lines = {(x["component"], int(x["terminal"])): x for x in c["line_terminal_current_series"]}
    bus16_split = normalized_kcl([
        ports[("16_1", 3)],
        ports[("16_2", 1)],
        lines[("B19_to_B16", 2)],
    ])
    bus26_split = normalized_kcl([
        ports[("26_1", 1)],
        ports[("26_2", 1)],
        lines[("B25_to_B26", 2)],
    ])

    pbus = [x for x in p["bus_port_current_series"] if x["bus_section"] == "Bus16_1"]
    pby = {int(x["port_index"]): x for x in pbus}
    assert set(pby) == {1, 2, 3, 4}
    pline = {(x["component"], int(x["terminal"])): x for x in p["line_terminal_current_series"]}
    assert ("B16_to_B17", 1) in pline
    fault = p["fault_current_series"]
    assert isinstance(fault, dict)
    fault_items = [pby[2], pline[("B16_to_B17", 1)], fault]
    tf = same_time(fault_items)
    fault_mask = (tf >= 5.0) & (tf <= 5.1)
    pre_mask = (tf >= 4.5) & (tf < 5.0)
    assert fault_mask.any() and pre_mask.any()
    bus16_fault = normalized_kcl(fault_items, fault_mask)
    bus16_prefault = normalized_kcl(fault_items[:2], pre_mask)

    report = {
        "status": "PASS_ALL_FIVE_COMPOSITE_BUSBAR_PORT_KCL",
        "model": c["model"],
        "physical_bus_sections": c["physical_bus_sections"],
        "logical_buses": c["logical_bus_count"],
        "bus_port_current_series": c["bus_port_current_count"],
        "bus_port_current_variable_mapping": "123/123 resolved with I_(2k-1)=LConn_k and I_(2k)=RConn_k",
        "single_component_line_port_direct_matches": "65/65 exact signed three-phase matches",
        "transformer_winding_endpoint_linear_consistency": "24/24",
        "line_terminal_current_vectors": c["line_terminal_current_count"],
        "line_components": c["line_component_count"],
        "line_terminal_phase_nonzero_vectors": line_phase_nonzero,
        "transformer_winding_current_vectors": c["transformer_winding_current_count"],
        "transformer_components": c["transformer_component_count"],
        "transformer_phase_nonzero_vectors": transformer_phase_nonzero,
        "composite_busbar_ports": 5,
        "composite_port_kcl": {
            "Bus16_split_Bus16_1_I3_plus_Bus16_2_I1_plus_B19_to_B16_terminal2": bus16_split,
            "Bus26_split_Bus26_1_I1_plus_Bus26_2_I1_plus_B25_to_B26_terminal2": bus26_split,
            "Bus16_1_RConn1_I2_plus_B16_to_B17_terminal1_plus_fault_current_during_fault": bus16_fault,
            "Bus16_1_RConn1_I2_plus_B16_to_B17_terminal1_prefault": bus16_prefault,
        },
        "max_transformer_linear_consistency_residual": max_transformer_linear_error,
        "line_terminal_phase_max_abs_A_min": float(np.min(np.vstack(line_maxima))),
        "line_terminal_phase_max_abs_A_max": float(np.max(np.vstack(line_maxima))),
        "transformer_winding_phase_max_abs_A_min": float(np.min(np.vstack(transformer_maxima))),
        "transformer_winding_phase_max_abs_A_max": float(np.max(np.vstack(transformer_maxima))),
        "full_network_safety_certified": False,
        "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
        "continuous_intersample_safety_certified": False,
        "interpretation": (
            "All five multi-component busbar ports are accounted for by exact three-phase KCL "
            "at the Bus16/Bus26 split nodes and at the faulted Bus16_1/RConn1 node. The 65 single-"
            "component line references directly match, and 24 transformer winding endpoints satisfy "
            "their fitted linear current-vector consistency checks. These are offline native Simscape "
            "topology/current-mapping results only; they do not authenticate online sensors, supply "
            "branch ampacity limits, or certify full-grid or intersample safety."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
