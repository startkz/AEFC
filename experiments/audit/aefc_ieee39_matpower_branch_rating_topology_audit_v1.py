#!/usr/bin/env python3
"""Map MATPOWER case39 reference RATE_A values to the native IEEE39 topology."""
from __future__ import annotations
import json
import pathlib
import re
from collections import Counter

ROOT=pathlib.Path(".")
RATINGS=ROOT/"configs/ieee39_matpower_case39_reference_branch_ratings.json"
MAPROOT=ROOT/"artifacts/current_map"
OUT=ROOT/"results/ieee39_safety_mapping/matpower_branch_rating_topology_match_v1.json"

def find_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return json.loads(hits[0].read_text(encoding="utf-8"))

def endpoints(name,kind):
    if kind=="line":
        m=re.fullmatch(r"B\s*(\d+)\s+to\s+B\s*(\d+)",name)
    else:
        m=re.fullmatch(r"TF\s+B\s*(\d+)\s+to\s+B\s*(\d+)",name)
    assert m,name
    return tuple(sorted((int(m.group(1)),int(m.group(2)))))

def main():
    r=json.loads(RATINGS.read_text(encoding="utf-8"))
    m=find_unique(MAPROOT,"native_ieee39_bus_port_current_variable_map_v2.json")
    assert r["system"]["branch_count"]==46
    assert r["system"]["line_branch_count"]==34
    assert r["system"]["transformer_branch_count"]==12
    assert m["resolved_physical_ports"]==123 and m["unresolved_physical_ports"]==0
    model_lines=sorted(set(x["component"] for x in m["line_terminal_signature_checks"]))
    model_tfs=sorted(set(x["component"] for x in m["transformer_current_signature_checks"]))
    assert len(model_lines)==34 and len(model_tfs)==12
    model_by_key={}
    for name in model_lines:
        key=("line",endpoints(name,"line"))
        assert key not in model_by_key,key
        model_by_key[key]=name
    for name in model_tfs:
        key=("transformer",endpoints(name,"transformer"))
        assert key not in model_by_key,key
        model_by_key[key]=name
    rating_by_key={}
    mapped=[]
    for b in r["branches"]:
        key=(b["type"],tuple(sorted((int(b["from_bus"]),int(b["to_bus"])))))
        assert key not in rating_by_key,key
        rating_by_key[key]=b
        assert key in model_by_key,("MATPOWER branch missing from MathWorks model",key)
        name=model_by_key[key]
        mapped.append({
            "branch_index":b["branch_index"],
            "from_bus":b["from_bus"],"to_bus":b["to_bus"],
            "type":b["type"],"native_component":name,
            "rateA_MVA":b["rateA_MVA"],"rateB_MVA":b["rateB_MVA"],
            "rateC_MVA":b["rateC_MVA"],
            "reference_from_end_rateA_current_A":b["from_end_rateA_current_A"],
            "reference_to_end_rateA_current_A":b["to_end_rateA_current_A"],
            "tap_ratio":b["tap_ratio"],
            "source_r_pu":b["r_pu"],"source_x_pu":b["x_pu"],
            "model_parameter_equivalence_verified":False,
            "thermal_limit_validated":False,
        })
    assert set(model_by_key)==set(rating_by_key),{
        "model_only":sorted(set(model_by_key)-set(rating_by_key)),
        "rating_only":sorted(set(rating_by_key)-set(model_by_key))}
    rates=Counter(str(x["rateA_MVA"]) for x in mapped)
    report={
      "status":"PASS_46_OF_46_MATPOWER_BRANCH_TOPOLOGY_MATCH",
      "source":r["source"],
      "native_model":m["model_source"],
      "baseMVA":r["system"]["baseMVA"],
      "all_reference_bus_base_kV":r["system"]["all_bus_base_kV_unique"],
      "mapped_line_components":sum(x["type"]=="line" for x in mapped),
      "mapped_transformer_components":sum(x["type"]=="transformer" for x in mapped),
      "matched_branch_count":len(mapped),
      "unmatched_branch_count":0,
      "rateA_MVA_distribution":dict(rates),
      "reference_rateA_current_A_range":[
        min(x["reference_from_end_rateA_current_A"] for x in mapped),
        max(x["reference_from_end_rateA_current_A"] for x in mapped)],
      "branch_mappings":mapped,
      "model_branch_R_X_equivalence_verified":False,
      "transformer_winding_base_voltage_equivalence_verified":False,
      "continuous_thermal_ampacity_validated":False,
      "full_network_safety_certified":False,
      "interpretation":(
        "All 34 native line components and 12 native transformer components match the 46 endpoint pairs "
        "in MATPOWER case39. RATE_A/B/C are mapped as reference MVA limits only. The MATPOWER case is a "
        "modified reference case whose comments attribute flow limits to the PSERC TC Calculator; the "
        "MathWorks component R/X/L/C parameters, winding voltage bases, RMS current convention, and "
        "continuous thermal capability have not yet been independently reconciled. Do not treat these "
        "reference limits as certified thermal limits of the native Simscape model."
      )
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","mapped_line_components","mapped_transformer_components","matched_branch_count","unmatched_branch_count","reference_rateA_current_A_range")},indent=2))

if __name__=="__main__":
    main()
