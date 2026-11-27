#!/usr/bin/env python3
"""Join physical Busbar port handles to native Simscape Bus/I# current series."""
from __future__ import annotations
import csv, hashlib, json, math, pathlib, re
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLD_ROOT = ROOT / "artifacts/busbar_port_map"
RAW_ROOT = ROOT / "artifacts/current_port_map"
OUT = ROOT / "results/ieee39_safety_mapping"
OLD_NAME = "native_busbar_port_component_map_v1.json"
RAW_NAME = "native_ieee39_bus_port_connection_map_v1.json"

def find_one(root, name):
    hits = list(root.rglob(name))
    if len(hits) != 1:
        raise AssertionError(f"expected one {name} under {root}, found {len(hits)}")
    return hits[0]

def norm(s):
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def flatten(x):
    if isinstance(x, list):
        for v in x:
            yield from flatten(v)
    else:
        yield float(x)

def signed_relative_error(a, b):
    aa, bb = list(flatten(a)), list(flatten(b))
    assert len(aa) == len(bb)
    na = math.sqrt(sum(x*x for x in aa))
    nb = math.sqrt(sum(x*x for x in bb))
    den = max(na, nb, 1e-12)
    return min(
        ((sign, math.sqrt(sum((x-sign*y)**2 for x, y in zip(aa, bb))) / den)
         for sign in (1, -1)),
        key=lambda z: z[1],
    )

def max_abs(values):
    return max((abs(v) for v in flatten(values)), default=0.0)

def classify_component(name):
    if re.fullmatch(r"B\d+ to B\d+", name): return "transmission_line"
    if re.fullmatch(r"TF B\d+ to B\d+", name): return "transformer"
    if name.startswith("Load"): return "load"
    if name.startswith("Gen"): return "generator"
    if name == "Fault (Three-Phase)": return "fault"
    if name.startswith("Bus"): return "busbar_interconnect"
    return "other"

def main():
    old_path = find_one(OLD_ROOT, OLD_NAME)
    raw_path = find_one(RAW_ROOT, RAW_NAME)
    old = json.loads(old_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    assert old["busbar_blocks"] == 41
    assert old["busbar_physical_ports"] == 123
    assert old["busbar_ports_matched"] == 123
    assert old["busbar_ports_unresolved"] == 0
    assert old["unique_connected_line_blocks"] == 34
    assert old["unique_connected_transformer_blocks"] == 12
    assert len(old["busbar_port_mappings"]) == 123
    assert raw["bus_port_current_count"] == len(raw["bus_port_current_series"]) == 123
    assert raw["physical_bus_sections"] == 41 and raw["logical_bus_count"] == 39
    assert raw["line_component_count"] == 34 and raw["transformer_component_count"] == 12
    assert raw["branch_current_series_count"] == len(raw["branch_current_series"]) == 126

    raw_bus = {b["name"]: b for b in raw["bus_block_connectivity"]}
    assert len(raw_bus) == 41
    current_by_bus = defaultdict(dict)
    for rec in raw["bus_port_current_series"]:
        current_by_bus["Bus" + rec["bus_section"]][int(rec["port_index"])] = rec

    raw_branch_components = {rec["component"]: rec["component_type"] for rec in raw["branch_current_series"]}
    old_bus_names = {x["bus_block"].split("/")[-1] for x in old["busbar_port_mappings"]}
    assert old_bus_names == set(raw_bus), "bus-block names differ between model copies"

    rows, errors, connected_port_refs = [], [], []
    previous_candidate_mismatches = 0
    for item in old["busbar_port_mappings"]:
        bus = item["bus_block"].split("/")[-1]
        ptype = f'{item["bus_port_kind"]}{item["bus_port_index"]}'
        pc_matches = [p for p in raw_bus[bus]["port_connectivity"] if p["type"] == ptype]
        if len(pc_matches) != 1:
            errors.append({"bus": bus, "port_type": ptype, "error": "PortConnectivity match count", "count": len(pc_matches)})
            continue
        pc = pc_matches[0]
        ordinal = int(pc["index"])
        current = current_by_bus[bus].get(ordinal)
        if current is None:
            errors.append({"bus": bus, "port_type": ptype, "error": "missing I ordinal", "ordinal": ordinal})
            continue
        expected_path = f'{raw["model"]}/Grid/{bus}/I{ordinal}/series'
        if current["path"] != expected_path:
            errors.append({"bus": bus, "port_type": ptype, "error": "current path mismatch", "actual": current["path"], "expected": expected_path})

        old_connected = item["connected_ports"]
        old_names = {norm(cp["block_name"]) for cp in old_connected}
        pc_names = {norm(name.split("/")[-1]) for name in pc.get("src_blocks", []) + pc.get("dst_blocks", [])}
        if not pc_names.issubset(old_names):
            errors.append({"bus": bus, "port_type": ptype, "error": "topology disagreement",
                           "port_connectivity": sorted(pc_names), "physical_line_map": sorted(old_names)})

        connected = []
        for cp in old_connected:
            name = cp["block_name"]
            ctype = classify_component(name)
            connected.append({
                "component": name, "component_type": ctype,
                "component_port_kind": cp["port_kind"],
                "component_port_index": int(cp["port_index"]),
            })
            connected_port_refs.append((name, cp["port_kind"], int(cp["port_index"]), ctype))
        old_candidate = item.get("current_variable_candidate", "")
        current_variable = f"I{ordinal}"
        if old_candidate != current_variable:
            previous_candidate_mismatches += 1
        rows.append({
            "bus_section": bus, "logical_bus": str(item["logical_bus"]),
            "current_variable_candidate": current_variable, "current_series_path": current["path"],
            "port_ordinal": ordinal, "physical_port_type": ptype,
            "physical_port_kind": item["bus_port_kind"],
            "physical_port_index": int(item["bus_port_index"]),
            "port_connectivity_primary_blocks": pc.get("src_blocks", []) + pc.get("dst_blocks", []),
            "all_connected_components": connected,
            "connected_port_count": int(item["connected_port_count"]),
            "previous_local_candidate": old_candidate,
            "previous_local_candidate_was_wrong": old_candidate != current_variable,
        })

    assert not errors, errors[:10]
    assert len(rows) == 123 and len({r["current_series_path"] for r in rows}) == 123
    for bus, block in raw_bus.items():
        n = len(current_by_bus[bus])
        assert len(block["port_connectivity"]) == n, (bus, len(block["port_connectivity"]), n)
        assert sorted(current_by_bus[bus]) == list(range(1, n + 1)), (bus, sorted(current_by_bus[bus]))

    mapped_line_names = {norm(cp["component"]) for row in rows for cp in row["all_connected_components"] if cp["component_type"] == "transmission_line"}
    mapped_transformer_names = {norm(cp["component"]) for row in rows for cp in row["all_connected_components"] if cp["component_type"] == "transformer"}
    raw_line_names = {norm(k) for k, v in raw_branch_components.items() if v == "transmission_line"}
    raw_transformer_names = {norm(k) for k, v in raw_branch_components.items() if v == "transformer"}
    assert len(raw_line_names) == 34 and raw_line_names.issubset(mapped_line_names)
    assert len(raw_transformer_names) == 12 and raw_transformer_names.issubset(mapped_transformer_names)

    branch_lookup = {(x["component"], x["variable"]): x for x in raw["branch_current_series"]}
    anchors = []
    for bus, ordinal, component, winding in (
        ("Bus10", 1, "TF_B32_to_B10", "i2"),
        ("Bus12", 1, "TF_B11_to_B12", "i2"),
    ):
        a, b = current_by_bus[bus][ordinal], branch_lookup[(component, winding)]
        assert a["time_s"] == b["time_s"]
        sign, err = signed_relative_error(a["values_real"], b["values_real"])
        anchors.append({
            "bus": bus, "current_variable": f"I{ordinal}",
            "component": component, "winding_series": winding,
            "max_time_difference_s": max(abs(x-y) for x, y in zip(a["time_s"], b["time_s"])),
            "best_sign": sign, "normalized_l2_residual": err,
        })
    assert all(a["best_sign"] == -1 and a["normalized_l2_residual"] <= 1e-12 for a in anchors)

    line_records = [x for x in raw["branch_current_series"] if x["component_type"] == "transmission_line"]
    line_phase_stats = {}
    for phase in ("a", "b", "c"):
        vals = [max_abs(x["values_real"]) for x in line_records if x["phase"] == phase]
        line_phase_stats[phase] = {
            "series_count": len(vals),
            "component_count": len({x["component"] for x in line_records if x["phase"] == phase}),
            "min_series_max_abs_A": min(vals),
            "max_series_max_abs_A": max(vals),
            "series_below_1e-6_A": sum(v < 1e-6 for v in vals),
        }
    assert all(line_phase_stats[p]["series_count"] == 34 for p in ("a", "b", "c"))

    bus_component_rms_counts = [0, 0, 0]
    for rec in raw["bus_port_current_series"]:
        vals = rec["values_real"]
        for j in range(3):
            rms = math.sqrt(sum(float(row[j])**2 for row in vals) / len(vals))
            if rms > 1e-6:
                bus_component_rms_counts[j] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    json_out = OUT / "native_ieee39_bus_port_current_variable_map_v1.json"
    csv_out = OUT / "native_ieee39_bus_port_current_variable_map_v1.csv"
    audit_out = OUT / "bus_port_current_variable_join_audit_v1.json"
    ref_counts = Counter(ctype for _, _, _, ctype in connected_port_refs)
    unique_type_counts = Counter(ctype for _, _, _, ctype in set(connected_port_refs))
    multi_ports = [r for r in rows if r["connected_port_count"] > 1]

    mapping = {
        "status": "PASS_123_OF_123_PHYSICAL_PORT_TO_COMPONENT_TOPOLOGY_MAP",
        "official_model_source": old["model"], "current_series_model": raw["model"],
        "physical_bus_sections": 41, "logical_buses": 39,
        "bus_port_current_series": 123, "bus_ports_resolved": len(rows), "unresolved_bus_ports": 0,
        "unique_transmission_line_components": len(raw_line_names),
        "unique_transformer_components": len(raw_transformer_names), "branch_current_series": 126,
        "current_variable_index_rule": "Provisional hypothesis only: Busbar Simscape I# may follow the global PortConnectivity ordinal; all 123 assignments require terminal-current signature validation.",
        "current_variable_mapping_verified": False,
        "verification_basis": [
            "123/123 physical busbar ports are structurally resolved to connected components; I# Series counts match per block, but the port-index permutation is not yet validated.",
            "For all 41 Busbar blocks, PortConnectivity record count equals the I# Series count and indices are contiguous 1..N; this count correspondence alone does not establish I# ordering.",
            "Every PortConnectivity LConn/RConn type and local index matches the physical-port handle record; the Simscape I# to PortConnectivity ordinal correspondence remains a candidate.",
            "All 34 line and 12 transformer components in the current Series registry occur in the physical port map.",
            "Two LConn1 anchors are exact: Bus10/I1 versus negative TF_B32_to_B10/i2 and Bus12/I1 versus negative TF_B11_to_B12/i2; these do not validate the remaining 121 I# assignments."
        ],
        "previous_local_candidate_differs_from_global_ordinal": previous_candidate_mismatches,
        "physical_component_port_reference_counts": dict(ref_counts),
        "unique_physical_component_port_counts": dict(unique_type_counts),
        "multi_component_busbar_ports": len(multi_ports),
        "multi_component_busbar_port_details": [
            {"bus_section": r["bus_section"], "current_variable_candidate": r["current_variable_candidate"],
             "physical_port_type": r["physical_port_type"], "components": r["all_connected_components"]}
            for r in multi_ports
        ],
        "transformer_current_signature_anchors": anchors,
        "line_inductor_current_amplitude_phase_diagnostic": line_phase_stats,
        "bus_port_current_three_component_nonzero_counts": bus_component_rms_counts,
        "full_network_safety_certified": False,
        "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
        "interpretation": (
            "All 123 physical Busbar ports are structurally mapped to connected components. The I# to "
            "LConn/RConn assignment in this artifact is only a provisional global-ordinal candidate; two "
            "transformer LConn1 anchors match exactly, but the remaining assignments require terminal-current "
            "signature matching. The selected inductor_a amplitude series are near zero while all three "
            "bus-port current components are nonzero, so these internal line-current series are not validated "
            "branch thermal measurements. This is offline mapping, not authenticated online sensing or a "
            "safety certificate."
        ),
        "bus_port_current_variable_map": rows,
        "source_artifact_sha256": {
            "busbar_port_component_map": sha256(old_path),
            "bus_port_current_series": sha256(raw_path),
        },
    }
    json_out.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    fields = [
        "bus_section", "logical_bus", "current_variable_candidate", "current_series_path",
        "port_ordinal", "physical_port_type", "physical_port_kind", "physical_port_index",
        "port_connectivity_primary_blocks", "all_connected_components",
        "connected_port_count", "previous_local_candidate", "previous_local_candidate_was_wrong",
    ]
    with csv_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:
            flat = dict(row)
            flat["port_connectivity_primary_blocks"] = "; ".join(row["port_connectivity_primary_blocks"])
            flat["all_connected_components"] = "; ".join(
                f'{x["component"]}({x["component_port_kind"]}{x["component_port_index"]})'
                for x in row["all_connected_components"]
            )
            w.writerow({k: flat.get(k) for k in fields})
    audit = {
        "status": mapping["status"], "bus_ports_resolved": len(rows), "unresolved_bus_ports": 0,
        "line_components": len(raw_line_names), "transformer_components": len(raw_transformer_names),
        "branch_current_series": len(raw["branch_current_series"]),
        "previous_local_candidate_differs_from_global_ordinal": previous_candidate_mismatches,
        "transformer_current_signature_anchors": anchors,
        "line_inductor_current_amplitude_phase_diagnostic": line_phase_stats,
        "multi_component_busbar_ports": len(multi_ports),
        "full_network_safety_certified": False, "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
    }
    audit_out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))

if __name__ == "__main__":
    main()
