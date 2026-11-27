#!/usr/bin/env python3
"""Compare native Simscape IEEE39 branch parameters with MATPOWER case39."""
from __future__ import annotations
import json, math, pathlib, re

ROOT=pathlib.Path(".")
PARAM_ROOT=ROOT/"artifacts/native_params"
RATING_PATH=ROOT/"configs/ieee39_matpower_case39_reference_branch_ratings.json"
OUT=ROOT/"results/ieee39_safety_mapping/native_matpower_parameter_equivalence_v1.json"

def find_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return json.loads(hits[0].read_text(encoding="utf-8"))

def param_map(x):
    rows=x.get("dialog_parameters",[])
    if isinstance(rows,dict): rows=[rows]
    return {q["name"]:q.get("value","") for q in rows}

def num(p,k):
    return float(p[k])

def key_from_name(name,kind):
    if kind=="line":
        m=re.fullmatch(r"B(\d+) to B(\d+)",name)
    else:
        m=re.fullmatch(r"TF B(\d+) to B(\d+)",name)
    assert m,name
    return (kind,tuple(sorted((int(m.group(1)),int(m.group(2))))))

def relerr(a,b):
    return abs(a-b)/max(abs(b),1e-12)

def main():
    native=find_unique(PARAM_ROOT,"native_ieee39_branch_parameter_inventory_v1.json")
    ref=json.loads(RATING_PATH.read_text(encoding="utf-8"))
    assert native["line_component_count"]==34 and native["transformer_component_count"]==12
    assert ref["system"]["baseMVA"]==100
    assert ref["system"]["all_bus_base_kV_unique"]==[345]
    branches={}
    for b in ref["branches"]:
        key=(b["type"],tuple(sorted((int(b["from_bus"]),int(b["to_bus"])))))
        assert key not in branches
        branches[key]=b
    zbase=(345e3**2)/(100e6)

    line_results=[]
    for x in native["line_components"]:
        p=param_map(x);key=key_from_name(x["name"],"line");b=branches[key]
        length=num(p,"length")
        assert p["length_unit"]=="km"
        f=num(p,"freq");assert math.isclose(f,60.0,abs_tol=1e-12)
        assert p["R_unit"]=="Ohm/km" and p["Rm_unit"]=="Ohm/km"
        assert p["L_unit"]=="mH/km" and p["M_unit"]=="mH/km"
        assert p["Cl_unit"]=="uF/km" and p["Cg_unit"]=="uF/km"
        rpu=(num(p,"R")-num(p,"Rm"))*length/zbase
        l1=(num(p,"L")-num(p,"M"))*1e-3
        xpu=2*math.pi*f*l1*length/zbase
        c1=(num(p,"Cg")+3*num(p,"Cl"))*1e-6
        bpu=2*math.pi*f*c1*length*zbase
        line_results.append({
          "native_component":x["name"],"branch_index":b["branch_index"],
          "from_bus":b["from_bus"],"to_bus":b["to_bus"],
          "native_positive_sequence_r_pu":rpu,"matpower_r_pu":b["r_pu"],
          "native_positive_sequence_x_pu":xpu,"matpower_x_pu":b["x_pu"],
          "native_positive_sequence_b_pu":bpu,"matpower_b_pu":b["b_pu"],
          "r_relative_error":relerr(rpu,b["r_pu"]),
          "x_relative_error":relerr(xpu,b["x_pu"]),
          "b_relative_error":relerr(bpu,b["b_pu"]),
          "rateA_MVA":b["rateA_MVA"],
          "rateA_current_reference_A_at_345kV":b["from_end_rateA_current_A"]
        })
    assert len(line_results)==34
    max_r=max(x["r_relative_error"] for x in line_results)
    max_x=max(x["x_relative_error"] for x in line_results)
    max_b=max(x["b_relative_error"] for x in line_results)
    line_pass=max_r<=1e-3 and max_x<=1e-2 and max_b<=5e-2
    assert line_pass,(max_r,max_x,max_b)

    transformer_results=[]
    for x in native["transformer_components"]:
        p=param_map(x);key=key_from_name(x["name"],"transformer");b=branches[key]
        rpu=num(p,"pu_Rw1")+num(p,"pu_Rw2")
        xpu=num(p,"pu_Xl1")+num(p,"pu_Xl2")
        transformer_results.append({
          "native_component":x["name"],"branch_index":b["branch_index"],
          "from_bus":b["from_bus"],"to_bus":b["to_bus"],
          "native_winding_resistance_sum_pu":rpu,"matpower_r_pu":b["r_pu"],
          "native_leakage_reactance_sum_pu":xpu,"matpower_x_pu":b["x_pu"],
          "r_absolute_error":abs(rpu-b["r_pu"]),
          "x_absolute_error":abs(xpu-b["x_pu"]),
          "native_SRated":p.get("SRated"),"native_SRated_unit":p.get("SRated_unit"),
          "native_VRated1":p.get("VRated1"),"native_VRated1_unit":p.get("VRated1_unit"),
          "native_VRated2":p.get("VRated2"),"native_VRated2_unit":p.get("VRated2_unit"),
          "native_Winding1Connection":p.get("Winding1Connection"),
          "native_Winding2Connection":p.get("Winding2Connection"),
          "matpower_tap_ratio":b["tap_ratio"],"matpower_rateA_MVA":b["rateA_MVA"],
          "tap_equivalence_verified":False,
          "thermal_rating_equivalence_verified":False
        })
    assert len(transformer_results)==12
    max_tr_r=max(x["r_absolute_error"] for x in transformer_results)
    max_tr_x=max(x["x_absolute_error"] for x in transformer_results)
    transformer_impedance_pass=max_tr_r<=1e-4+1e-12 and max_tr_x<=1e-10
    assert transformer_impedance_pass,(max_tr_r,max_tr_x)

    report={
      "status":"PASS_NATIVE_LINE_AND_TRANSFORMER_SERIES_IMPEDANCE_EQUIVALENCE",
      "source_inventory_run_id":45931696089,
      "matpower_source":ref["source"],
      "system_base":{"baseMVA":100,"baseKV":345,"frequency_Hz":60,"Zbase_ohm":zbase},
      "line_parameter_equivalence":{
        "matched_lines":34,"r_x_b_all_within_tolerance":True,
        "tolerances":{"r_relative":1e-3,"x_relative":1e-2,"b_relative":5e-2},
        "max_relative_errors":{"r":max_r,"x":max_x,"b":max_b},
        "line_results":line_results,
        "rateA_reference_applicable_to_line_benchmark":True,
        "continuous_thermal_ampacity_certified":False
      },
      "transformer_parameter_equivalence":{
        "matched_transformers":12,"winding_R_X_all_within_tolerance":True,
        "max_absolute_errors":{"r_pu":max_tr_r,"x_pu":max_tr_x},
        "transformer_results":transformer_results,
        "tap_equivalence_verified":False,
        "native_SRated_thermal_limit_verified":False,
        "matpower_RATE_A_applied_to_transformer_windings":False
      },
      "full_network_safety_certified":False,
      "interpretation":(
        "All 34 native three-phase line blocks reproduce MATPOWER case39 positive-sequence R/X/B "
        "within the stated tolerances using R1=R-Rm, L1=L-M and C1=Cg+3Cl. All 12 native transformer "
        "blocks reproduce the MATPOWER branch winding-resistance/leakage-reactance sums within the "
        "stated absolute tolerances. MATPOWER RATE_A can therefore be used as a benchmark reference for "
        "the 34 345-kV lines after RMS-current calculation, but it is not a thermal certification. "
        "Transformer winding thermal limits must use the native winding ratings/voltage bases and "
        "cannot be inferred from MATPOWER branch RATE_A; the 100-MW SRated parameter and tap/voltage "
        "equivalence require separate review."
      )
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":report["status"],"matched_lines":34,"matched_transformers":12,
      "max_line_relative_errors":report["line_parameter_equivalence"]["max_relative_errors"],
      "max_transformer_absolute_errors":report["transformer_parameter_equivalence"]["max_absolute_errors"],
      "rateA_reference_applicable_to_line_benchmark":True,
      "transformer_thermal_rating_verified":False
    },indent=2))

if __name__=="__main__":
    main()
