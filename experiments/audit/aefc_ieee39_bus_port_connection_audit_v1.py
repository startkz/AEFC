#!/usr/bin/env python3
"""Count and expose structural evidence for the IEEE39 bus-port connection map."""
from __future__ import annotations
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "results/ieee39_safety_mapping/native_ieee39_bus_port_connection_map_v1.json"
OUT = ROOT / "results/ieee39_safety_mapping/bus_port_connection_audit_v1.json"

def names(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x if str(v)]
    return [str(x)] if str(x) else []

def main():
    if not SOURCE.is_file():
        raise SystemExit(f"missing raw connection evidence: {SOURCE}")
    d = json.loads(SOURCE.read_text(encoding="utf-8"))
    ports = d["bus_port_current_series"]
    branches = d["branch_current_series"]
    assert len(ports) == d["bus_port_current_count"] == 123
    assert len(branches) == d["branch_current_series_count"] == 126
    assert d["line_component_count"] == 34
    assert d["transformer_component_count"] == 12
    assert d["physical_bus_sections"] == 41
    assert d["logical_bus_count"] == 39

    paths = [x["path"] for x in ports + branches]
    assert len(paths) == len(set(paths)), "duplicate current series paths"
    for x in ports:
        assert x["unit"] == "A"
        assert len(x["time_s"]) >= 2
        assert len(x["values_real"]) == len(x["time_s"])
        assert len(x["values_real"][0]) == 3
    for x in branches:
        assert x["unit"] == "A"
        assert len(x["time_s"]) >= 2
        assert len(x["values_real"]) == len(x["time_s"])

    line_components = sorted({x["component"] for x in branches if x["component_type"] == "transmission_line"})
    transformer_components = sorted({x["component"] for x in branches if x["component_type"] == "transformer"})
    assert len(line_components) == 34
    assert len(transformer_components) == 12
    assert sum(x["component_type"] == "transmission_line" for x in branches) == 102
    assert sum(x["component_type"] == "transformer" for x in branches) == 24

    component_names = set(line_components + transformer_components)
    block_records = []
    structural_edges = []
    for category in ("bus_block_connectivity", "line_block_connectivity", "transformer_block_connectivity"):
        for b in d.get(category, []):
            block_records.append(b)
            if category != "bus_block_connectivity":
                continue
            bus_section = b.get("name", "")
            connected = set()
            for rec in b.get("port_connectivity", []) or []:
                for key in ("src_blocks", "dst_blocks"):
                    for raw in names(rec.get(key)):
                        base = raw.rstrip("/").split("/")[-1]
                        if base in component_names:
                            connected.add(base)
                            structural_edges.append({
                                "bus_section": bus_section,
                                "port_connectivity_index": rec.get("index"),
                                "connectivity_type": rec.get("type"),
                                "component": base,
                                "source_field": key,
                            })
            for rec in b.get("port_handles", []) or []:
                for key in ("line_src_blocks", "line_dst_blocks"):
                    for raw in names(rec.get(key)):
                        base = raw.rstrip("/").split("/")[-1]
                        if base in component_names:
                            connected.add(base)
                            structural_edges.append({
                                "bus_section": bus_section,
                                "port_handle_field": rec.get("field"),
                                "port_number": rec.get("port_number"),
                                "component": base,
                                "source_field": key,
                            })
            b["structurally_connected_branch_components"] = sorted(connected)

    # Summarize whether every branch endpoint appears in direct block
    # connectivity. Do not infer a port-index mapping from order alone.
    endpoint_pairs = []
    for component in line_components + transformer_components:
        m = re.match(r"(?:TF_)?B(\d+)_to_B(\d+)$", component)
        if m:
            endpoint_pairs.extend([(component, m.group(1)), (component, m.group(2))])
    structural_component_set = {x["component"] for x in structural_edges}
    mapped_components = sorted(component_names & structural_component_set)

    report = {
        "status": "PASS_CURRENT_SERIES_AND_CONNECTIVITY_CAPTURE",
        "model": d["model"],
        "capture_stop_time_s": d["capture_stop_time_s"],
        "bus_port_current_series": len(ports),
        "physical_bus_sections": d["physical_bus_sections"],
        "logical_bus_count": d["logical_bus_count"],
        "line_components": len(line_components),
        "line_phase_current_series": 102,
        "transformer_components": len(transformer_components),
        "transformer_winding_current_series": 24,
        "branch_current_series": len(branches),
        "unique_current_series_paths": len(paths),
        "simulink_bus_blocks_found": d["simulink_bus_block_count"],
        "simulink_line_blocks_found": d["simulink_line_block_count"],
        "simulink_transformer_blocks_found": d["simulink_transformer_block_count"],
        "direct_structural_bus_to_branch_edges": len(structural_edges),
        "branch_components_with_any_direct_structural_edge": len(mapped_components),
        "branch_components_missing_direct_structural_edge": sorted(component_names - structural_component_set),
        "structural_edges": structural_edges,
        "bus_blocks": d.get("bus_block_connectivity", []),
        "line_blocks": d.get("line_block_connectivity", []),
        "transformer_blocks": d.get("transformer_block_connectivity", []),
        "interpretation": (
            "This is a complete capture of the requested current-series families and available "
            "Simulink port-connectivity metadata. A port-number-to-component mapping is not "
            "certified unless direct topology and signed-current correspondence can be verified; "
            "block port ordering alone is not treated as proof."
        ),
        "full_network_safety_certified": False,
        "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "status", "bus_port_current_series", "line_components",
        "line_phase_current_series", "transformer_components",
        "transformer_winding_current_series", "branch_current_series",
        "simulink_bus_blocks_found", "direct_structural_bus_to_branch_edges",
        "branch_components_with_any_direct_structural_edge",
        "branch_components_missing_direct_structural_edge")}, indent=2))

if __name__ == "__main__":
    main()
