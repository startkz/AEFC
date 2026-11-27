#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, itertools, json, math, pathlib, re
from collections import Counter, defaultdict
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLD_ROOT = ROOT / "artifacts/busbar_port_map"
RAW_ROOT = ROOT / "artifacts/current_port_map"
TERM_ROOT = ROOT / "artifacts/terminal_current_capture"
OUT = ROOT / "results/ieee39_safety_mapping"

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

def classify(name):
    if re.fullmatch(r"B\d+ to B\d+", name): return "transmission_line"
    if re.fullmatch(r"TF B\d+ to B\d+", name): return "transformer"
    if name.startswith("Load"): return "load"
    if name.startswith("Gen"): return "generator"
    if name == "Fault (Three-Phase)": return "fault"
    if name.startswith("Bus"): return "busbar_interconnect"
    return "other"

def direct_match(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3:
        return {"error": 1e9, "sign": None, "permutation": None}
    best = {"error": 1e9, "sign": None, "permutation": None}
    den = max(float(np.linalg.norm(a)), float(np.linalg.norm(b)), 1e-12)
    for perm in itertools.permutations(range(3)):
        bp = b[:, perm]
        for sign in (1, -1):
            err = float(np.linalg.norm(a - sign * bp) / den)
            if err < best["error"]:
                best = {"error": err, "sign": sign, "permutation": list(perm)}
    return best

def linear_match(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3:
        return {"error": 1e9, "rank": 0, "matrix": None}
    matrix, _, rank, _ = np.linalg.lstsq(b, a, rcond=None)
    pred = b @ matrix
    den = max(float(np.linalg.norm(a)), float(np.linalg.norm(pred)), 1e-12)
    return {"error": float(np.linalg.norm(a - pred) / den),
            "rank": int(rank), "matrix": matrix.tolist()}

def interleaved_index(kind, local_index):
    return 2 * (int(local_index) - 1) + (1 if kind == "LConn" else 2)

def best_line_match(current, line_series):
    candidates = []
    for rec in line_series:
        dm = direct_match(current, rec["values_real"])
        candidates.append({
            "terminal": int(rec["terminal"]),
            "direct_error": dm["error"],
            "sign": dm["sign"],
            "phase_permutation": dm["permutation"],
        })
    return min(candidates, key=lambda x: x["direct_error"])

def main():
    old_path = find_one(OLD_ROOT, "native_busbar_port_component_map_v1.json")
    raw_path = find_one(RAW_ROOT, "native_ieee39_bus_port_connection_map_v1.json")
    term_path = find_one(TERM_ROOT, "native_ieee39_bus_port_terminal_current_capture_v2.json")
    old = json.loads(old_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    term = json.loads(term_path.read_text(encoding="utf-8"))

    assert old["busbar_blocks"] == 41 and old["busbar_physical_ports"] == 123
    assert old["busbar_ports_matched"] == 123 and old["busbar_ports_unresolved"] == 0
    assert len(old["busbar_port_mappings"]) == 123
    assert raw["bus_port_current_count"] == 123
    assert raw["physical_bus_sections"] == 41 and raw["logical_bus_count"] == 39
    assert term["bus_port_current_count"] == len(term["bus_port_current_series"]) == 123
    assert term["line_terminal_current_count"] == len(term["line_terminal_current_series"]) == 68
    assert term["line_component_count"] == 34
    assert term["transformer_winding_current_count"] == len(term["transformer_winding_current_series"]) == 24
    assert term["transformer_component_count"] == 12

    current_by_bus = defaultdict(dict)
    for rec in term["bus_port_current_series"]:
        current_by_bus["Bus" + rec["bus_section"]][int(rec["port_index"])] = rec
    line_by_component = defaultdict(list)
    for rec in term["line_terminal_current_series"]:
        line_by_component[rec["component"]].append(rec)
    transformer_by_component = defaultdict(list)
    for rec in term["transformer_winding_current_series"]:
        transformer_by_component[rec["component"]].append(rec)
    raw_bus = {b["name"]: b for b in raw["bus_block_connectivity"]}
    assert len(raw_bus) == 41
    pc_by_bus = {
        bus: {p["type"]: int(p["index"]) for p in block["port_connectivity"]}
        for bus, block in raw_bus.items()
    }

    rows, line_refs, transformer_refs = [], [], []
    unique_line_endpoint_matches = {}
    unique_transformer_endpoint_matches = {}
    port_refs = []
    old_candidate_diffs = 0
    for item in old["busbar_port_mappings"]:
        bus = item["bus_block"].split("/")[-1]
        kind = item["bus_port_kind"]
        local_index = int(item["bus_port_index"])
        ptype = f"{kind}{local_index}"
        expected_idx = interleaved_index(kind, local_index)
        current = current_by_bus[bus].get(expected_idx)
        assert current is not None, (bus, ptype, expected_idx)
        assert current["path"].endswith(f"/{bus}/I{expected_idx}/series")
        pc_idx = pc_by_bus[bus][ptype]
        local_candidate = int(item["current_variable_candidate"][1:])
        if local_candidate != expected_idx:
            old_candidate_diffs += 1

        connected = []
        line_match = None
        transformer_match = None
        for cp in item["connected_ports"]:
            cname = cp["block_name"]
            ctype = classify(cname)
            cp_row = {
                "component": cname, "component_type": ctype,
                "component_port_kind": cp["port_kind"],
                "component_port_index": int(cp["port_index"]),
            }
            connected.append(cp_row)
            if ctype == "transmission_line":
                comp = next(k for k in line_by_component if norm(k) == norm(cname))
                sigs = line_by_component[comp]
                lm = best_line_match(current["values_real"], sigs)
                ref = {
                    "bus": bus, "bus_port": ptype, "current_variable": f"I{expected_idx}",
                    "component": cname, "component_port": f'{cp["port_kind"]}{cp["port_index"]}',
                    **lm, "multi_component_bus_port": int(item["connected_port_count"]) > 1,
                }
                line_refs.append(ref)
                ep = (cname, cp["port_kind"], int(cp["port_index"]))
                prev = unique_line_endpoint_matches.get(ep)
                if prev is None or ref["direct_error"] < prev["direct_error"]:
                    unique_line_endpoint_matches[ep] = ref
                if line_match is None or lm["direct_error"] < line_match["direct_error"]:
                    line_match = {**lm, "component": cname,
                                  "component_port": f'{cp["port_kind"]}{cp["port_index"]}'}
            elif ctype == "transformer":
                comp = next(k for k in transformer_by_component if norm(k) == norm(cname))
                candidates = []
                for winding in transformer_by_component[comp]:
                    dm = direct_match(current["values_real"], winding["values_real"])
                    lm = linear_match(current["values_real"], winding["values_real"])
                    candidates.append({
                        "winding": winding["winding"],
                        "direct_error": dm["error"],
                        "direct_sign": dm["sign"],
                        "direct_phase_permutation": dm["permutation"],
                        "linear_error": lm["error"],
                        "linear_rank": lm["rank"],
                    })
                best = min(candidates, key=lambda x: x["direct_error"])
                best_linear = min(candidates, key=lambda x: x["linear_error"])
                tr = {
                    "bus": bus, "bus_port": ptype, "current_variable": f"I{expected_idx}",
                    "component": cname, "component_port": f'{cp["port_kind"]}{cp["port_index"]}',
                    "best_direct": best, "best_linear": best_linear,
                }
                transformer_refs.append(tr)
                ep = (cname, cp["port_kind"], int(cp["port_index"]))
                unique_transformer_endpoint_matches[ep] = tr
                if transformer_match is None or best_linear["linear_error"] < transformer_match["linear_error"]:
                    transformer_match = tr

        if item["connected_port_count"] > 1:
            sig_status = "COMPOSITE_PORT_CURRENT_SUM_PENDING"
        elif line_match and line_match["direct_error"] <= 1e-8:
            sig_status = "LINE_TERMINAL_DIRECT_MATCH"
        elif transformer_match and transformer_match["best_linear"]["linear_error"] <= 1e-8:
            sig_status = "TRANSFORMER_WINDING_LINEAR_MATCH"
        elif line_match:
            sig_status = "LINE_TERMINAL_MATCH_REVIEW"
        elif transformer_match:
            sig_status = "TRANSFORMER_WINDING_MATCH_REVIEW"
        else:
            sig_status = "STRUCTURAL_PORT_ORDER_ASSIGNED"

        rows.append({
            "bus_section": bus, "logical_bus": str(item["logical_bus"]),
            "current_variable": f"I{expected_idx}",
            "current_series_path": current["path"],
            "port_order": expected_idx,
            "physical_port_type": ptype,
            "physical_port_kind": kind,
            "physical_port_index": local_index,
            "port_connectivity_index": pc_idx,
            "previous_local_candidate": f"I{local_candidate}",
            "previous_local_candidate_differs": local_candidate != expected_idx,
            "connected_port_count": int(item["connected_port_count"]),
            "connected_components": connected,
            "line_terminal_match": line_match,
            "transformer_winding_match": transformer_match,
            "signature_status": sig_status,
        })
        port_refs.extend((cp["block_name"], cp["port_kind"], int(cp["port_index"]), classify(cp["block_name"]))
                         for cp in item["connected_ports"])

    assert len(rows) == 123
    assert len({r["current_series_path"] for r in rows}) == 123
    # Every bus block has exactly the interleaved I# set predicted by its physical ports.
    for bus, block in raw_bus.items():
        expected = sorted(interleaved_index(
            x["bus_port_kind"], x["bus_port_index"])
            for x in old["busbar_port_mappings"] if x["bus_block"].split("/")[-1] == bus)
        actual = sorted(current_by_bus[bus])
        assert expected == actual, (bus, expected, actual)

    # Validate the interleaved order against direct line terminal signatures.
    assert len(line_refs) == 70
    exact_line_refs = [x for x in line_refs if x["direct_error"] <= 1e-8]
    assert len(exact_line_refs) == 65
    assert len(unique_line_endpoint_matches) == 68
    exact_unique_line = [x for x in unique_line_endpoint_matches.values() if x["direct_error"] <= 1e-8]
    composite_line_endpoints = [x for x in unique_line_endpoint_matches.values() if x["direct_error"] > 1e-8]
    assert len(exact_unique_line) == 65 and len(composite_line_endpoints) == 3
    assert all(x["multi_component_bus_port"] for x in line_refs if x["direct_error"] > 1e-8)

    # For single-component line ports, LConn1 is phase_splitter1 and RConn1 is phase_splitter2.
    single_line_refs = [x for x in line_refs if not x["multi_component_bus_port"]]
    assert len(single_line_refs) == 65
    assert all(x["direct_error"] <= 1e-8 for x in single_line_refs)
    lconn_matches = [x for x in single_line_refs if x["component_port"] == "LConn1"]
    rconn_matches = [x for x in single_line_refs if x["component_port"] == "RConn1"]
    assert len(lconn_matches) == 33 and all(x["terminal"] == 1 for x in lconn_matches)
    assert len(rconn_matches) == 32 and all(x["terminal"] == 2 for x in rconn_matches)

    # Transformer winding current consistency.
    assert len(transformer_refs) == 24 and len(unique_transformer_endpoint_matches) == 24
    transformer_direct = [x for x in transformer_refs if x["best_direct"]["direct_error"] <= 1e-8]
    transformer_linear = [x for x in transformer_refs if x["best_linear"]["linear_error"] <= 1e-8]
    assert len(transformer_direct) == 11 and len(transformer_linear) == 24

    # Compare with the two rejected ordering hypotheses.
    global_matches = 0
    local_matches = 0
    for item in old["busbar_port_mappings"]:
        bus = item["bus_block"].split("/")[-1]
        for cp in item["connected_ports"]:
            if classify(cp["block_name"]) != "transmission_line":
                continue
            comp = next(k for k in line_by_component if norm(k) == norm(cp["block_name"]))
            for rule in ("global", "local"):
                idx = pc_by_bus[bus][f'{item["bus_port_kind"]}{item["bus_port_index"]}'] if rule == "global" else int(item["current_variable_candidate"][1:])
                candidate = current_by_bus[bus][idx]["values_real"]
                err = best_line_match(candidate, line_by_component[comp])["direct_error"]
                if err <= 1e-8:
                    if rule == "global": global_matches += 1
                    else: local_matches += 1
    assert global_matches == 33 and local_matches == 24

    ref_counts = Counter(x[3] for x in port_refs)
    unique_component_ports = set(port_refs)
    unique_type_counts = Counter(x[3] for x in unique_component_ports)
    multi_ports = [r for r in rows if r["connected_port_count"] > 1]
    assert len(multi_ports) == 5
    assert old_candidate_diffs == 82

    OUT.mkdir(parents=True, exist_ok=True)
    json_out = OUT / "native_ieee39_bus_port_current_variable_map_v2.json"
    csv_out = OUT / "native_ieee39_bus_port_current_variable_map_v2.csv"
    audit_out = OUT / "bus_port_current_variable_join_audit_v2.json"

    mapping = {
        "status": "PASS_INTERLEAVED_123_PORT_CURRENT_VARIABLE_MAP",
        "model_source": old["model"],
        "current_series_model": term["model"],
        "physical_bus_sections": 41, "logical_buses": 39,
        "bus_port_current_series": 123, "resolved_physical_ports": 123, "unresolved_physical_ports": 0,
        "unique_transmission_line_components": 34, "unique_line_component_ports": 68,
        "unique_transformer_components": 12, "unique_transformer_component_ports": 24,
        "line_terminal_current_vectors": 68, "transformer_winding_current_vectors": 24,
        "current_variable_order_rule": "I_(2k-1) maps to LConn_k; I_(2k) maps to RConn_k.",
        "current_variable_mapping_verified": True,
        "mapping_scope": "Offline native Simscape port/current-variable mapping; not an authenticated online sensor or safety certificate.",
        "verification_summary": {
            "bus_blocks_with_exact_interleaved_I_set": 41,
            "bus_blocks_total": 41,
            "line_port_references": 70,
            "line_port_references_directly_matched": 65,
            "unique_line_component_ports": 68,
            "unique_line_component_ports_directly_matched": 65,
            "composite_line_component_endpoints": 3,
            "single_component_line_port_references": 65,
            "single_component_line_port_references_directly_matched": 65,
            "LConn1_to_phase_splitter1_matches": len(lconn_matches),
            "RConn1_to_phase_splitter2_matches": len(rconn_matches),
            "transformer_port_endpoints": 24,
            "transformer_endpoints_direct_signed_phase_matches": len(transformer_direct),
            "transformer_endpoints_linear_winding_consistency": len(transformer_linear),
            "global_PortConnectivity_ordinal_line_matches": global_matches,
            "previous_local_candidate_line_matches": local_matches,
            "previous_local_candidate_differs_from_interleaved_rule": old_candidate_diffs,
            "multi_component_busbar_ports": len(multi_ports),
        },
        "multi_component_busbar_port_details": [
            {"bus_section": r["bus_section"], "current_variable": r["current_variable"],
             "physical_port_type": r["physical_port_type"], "connected_components": r["connected_components"]}
            for r in multi_ports
        ],
        "composite_line_component_endpoints": composite_line_endpoints,
        "transformer_current_signature_checks": transformer_refs,
        "line_terminal_signature_checks": line_refs,
        "physical_component_port_reference_counts": dict(ref_counts),
        "unique_physical_component_port_counts": dict(unique_type_counts),
        "full_network_safety_certified": False,
        "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
        "composite_port_current_sum_fully_validated": False,
        "interpretation": (
            "The interleaved I# order is supported by exact terminal-current matching at all 65 single-component "
            "line-port references and by winding-current consistency at all 24 transformer endpoints. The five "
            "multi-component busbar ports are structurally assigned by the same port-order rule, but their net "
            "current sums require separate KCL/fault checks. The line terminal current vectors are phase_splitter1/2; "
            "the inductor_a internal amplitude series are not terminal phase-A currents. This mapping does not "
            "certify online sensor integrity, branch thermal limits, or full-network safety."
        ),
        "bus_port_current_variable_map": rows,
        "source_artifact_sha256": {
            "physical_busbar_port_map": sha256(old_path),
            "bus_port_current_capture": sha256(find_one(RAW_ROOT, "native_ieee39_bus_port_connection_map_v1.json")),
            "terminal_current_capture": sha256(term_path),
        },
    }
    json_out.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    fields = [
        "bus_section", "logical_bus", "current_variable", "current_series_path",
        "port_order", "physical_port_type", "physical_port_kind", "physical_port_index",
        "port_connectivity_index", "previous_local_candidate", "previous_local_candidate_differs",
        "connected_port_count", "connected_components", "line_terminal_match",
        "transformer_winding_match", "signature_status",
    ]
    with csv_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:
            flat = dict(row)
            flat["connected_components"] = "; ".join(
                f'{x["component"]}({x["component_port_kind"]}{x["component_port_index"]})'
                for x in row["connected_components"])
            flat["line_terminal_match"] = json.dumps(row["line_terminal_match"], separators=(",", ":"))
            flat["transformer_winding_match"] = json.dumps(row["transformer_winding_match"], separators=(",", ":"))
            w.writerow({k: flat.get(k) for k in fields})

    audit = {
        "status": mapping["status"],
        "bus_port_current_series": 123, "physical_ports_resolved": 123, "unresolved": 0,
        "interleaved_rule": "I_(2k-1)=LConn_k; I_(2k)=RConn_k",
        "bus_blocks_exact": "41/41",
        "line_port_references_direct_matches": "65/70",
        "unique_line_component_ports_direct_matches": "65/68",
        "transformer_port_endpoints_linear_consistency": "24/24",
        "transformer_port_endpoints_direct_matches": "11/24",
        "global_PortConnectivity_ordinal_line_matches": "33/70",
        "previous_local_candidate_line_matches": "24/70",
        "previous_local_candidate_differences": 82,
        "multi_component_busbar_ports": 5,
        "composite_port_current_sum_fully_validated": False,
        "full_network_safety_certified": False,
        "online_sensor_integrity_verified": False,
        "branch_thermal_limits_validated": False,
    }
    audit_out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))

if __name__ == "__main__":
    main()
