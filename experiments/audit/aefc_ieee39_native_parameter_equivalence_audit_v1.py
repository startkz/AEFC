#!/usr/bin/env python3
"""Compare native Simscape positive-sequence line and transformer parameters with MATPOWER case39."""
from __future__ import annotations
import json, math, pathlib, re

ROOT=pathlib.Path(".")
REF=ROOT/"configs/ieee39_matpower_case39_reference_branch_ratings.json"
NATIVE_ROOT=ROOT/"artifacts/native_branch_parameters"
OUT=ROOT/"results/ieee39_safety_mapping/native_matpower_parameter_equivalence_v1.json"

def load_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return json.loads(hits[0].read_text(encoding="utf-8"))

def params(block):
    rows=block.get("dialog_parameters",[])
    if isinstance(rows,dict): rows=[rows]
    return {x["name"]:x.get("value","") for x in rows}

def number(p,k):
    return float(p[k])

def endpoints(name,kind):
    if kind=="line":
        m=re.fullmatch(r"B\s*(\d+)\s+to\s+B\s*(\d+)",name)
    else:
        m=re.fullmatch(r"TF\s+B\s*(\d+)\s+to\s+B\s*(\d+)",name)
    assert m,name
    return tuple(sorted((int(m.group(1)),int(m.group(2)))))

def relerr(a,b):
    return abs(a-b)/max(abs(b),1e-12)

def main():
    ref=json.loads(REF.read_text(encoding="utf-8"))
    native=load_unique(NATIVE_ROOT,"native_ieee39_branch_parameter_inventory_v1.json")
    assert native["line_component_count"]==34 and native["transformer_component_count"]==12
    Sbase=ref["system"]["baseMVA"]
    kvset=ref["system"]["all_bus_base_kV_unique"]
    assert len(kvset)==1
    Vbase=float(kvset[0])
    Zbase=Vbase**2/Sbase
    lines={("line",endpoints(x["name"],"line")):x for x in native["line_components"]}
    transformers={("transformer",endpoints(x["name"],"transformer")):x for x in native["transformer_components"]}
    records=[]
    for b in ref["branches"]:
        key=(b["type"],tuple(sorted((int(b["from_bus"]),int(b["to_bus"])))))
        assert key in (lines if b["type"]=="line" else transformers),("missing native component",key)
        block=(lines if b["type"]=="line" else transformers)[key]
        p=params(block)
        rec={"branch_index":b["branch_index"],"from_bus":b["from_bus"],"to_bus":b["to_bus"],
             "type":b["type"],"native_component":block["name"],
             "matpower_r_pu":b["r_pu"],"matpower_x_pu":b["x_pu"],
             "matpower_b_pu":b["b_pu"],"matpower_tap_ratio":(b["tap_ratio"] if b["tap_ratio"] else 1.0),
             "matpower_rateA_MVA":b["rateA_MVA"]}
        if b["type"]=="line":
            length=number(p,"length")
            freq=number(p,"freq")
            assert p["length_unit"]=="km" and p["R_unit"]=="Ohm/km" and p["Rm_unit"]=="Ohm/km"
            assert p["L_unit"]=="mH/km" and p["M_unit"]=="mH/km"
            assert p["Cl_unit"]=="uF/km" and p["Cg_unit"]=="uF/km"
            r1=(number(p,"R")-number(p,"Rm"))*length
            l1=(number(p,"L")-number(p,"M"))*1e-3*length
            c1=(number(p,"Cg")+3*number(p,"Cl"))*1e-6*length
            x1=2*math.pi*freq*l1
            b1=2*math.pi*freq*c1*Zbase
            rpu=r1/Zbase;xpu=x1/Zbase
            rec.update({"native_frequency_Hz":freq,"length_km":length,
                "positive_sequence_R_ohm":r1,"positive_sequence_X_ohm":x1,
                "positive_sequence_C_F":c1,"native_r_pu":rpu,"native_x_pu":xpu,
                "native_b_pu":b1,"r_relative_error":relerr(rpu,b["r_pu"]),
                "x_relative_error":relerr(xpu,b["x_pu"]),
                "b_relative_error":relerr(b1,b["b_pu"]),
                "r_match":relerr(rpu,b["r_pu"])<=2e-4,
                "x_match":relerr(xpu,b["x_pu"])<=2e-4,
                "b_match":relerr(b1,b["b_pu"])<=2e-4,
                "line_positive_sequence_equivalence":(
                    relerr(rpu,b["r_pu"])<=2e-4 and relerr(xpu,b["x_pu"])<=2e-4 and relerr(b1,b["b_pu"])<=2e-4)})
        else:
            S=float(number(p,"SRated"))
            v1=float(number(p,"VRated1"));v2=float(number(p,"VRated2"))
            rpu=number(p,"pu_Rw1")+number(p,"pu_Rw2")
            xpu=number(p,"pu_Xl1")+number(p,"pu_Xl2")
            # All MATPOWER case39 buses are assigned 345 kV. The model's
            # actual transformer winding ratings must be compared against
            # those bases before interpreting the per-unit tap.
            basef=float(b["from_bus_base_kV"]);baset=float(b["to_bus_base_kV"])
            model_tap=(v1/v2)/(basef/baset)
            tap_err=relerr(model_tap,rec["matpower_tap_ratio"])
            rec.update({"native_SRated":S,"native_SRated_unit":p.get("SRated_unit"),
                "native_VRated1_kV":v1,"native_VRated2_kV":v2,
                "native_winding1_connection":p.get("Winding1Connection"),
                "native_winding2_connection":p.get("Winding2Connection"),
                "native_r_pu_sum_windings":rpu,"native_x_pu_sum_windings":xpu,
                "r_relative_error":relerr(rpu,b["r_pu"]),
                "x_relative_error":relerr(xpu,b["x_pu"]),
                "native_tap_ratio_relative_to_matpower_bus_bases":model_tap,
                "tap_relative_error":tap_err,
                "native_winding1_matches_matpower_from_bus_base":abs(v1-basef)<=1e-6,
                "native_winding2_matches_matpower_to_bus_base":abs(v2-baset)<=1e-6,
                "series_r_match":relerr(rpu,b["r_pu"])<=2e-4,
                "series_x_match":relerr(xpu,b["x_pu"])<=2e-4,
                "tap_match":tap_err<=2e-4,
                "winding_voltage_base_match":abs(v1-basef)<=1e-6 and abs(v2-baset)<=1e-6,
                "native_transformer_rating_matches_rateA":False,
                "rating_comparison_note":"SRated is reported in MW by the native block; MATPOWER RATE_A is MVA. No direct equality is asserted."})
        records.append(rec)
    line=[x for x in records if x["type"]=="line"]
    tf=[x for x in records if x["type"]=="transformer"]
    assert len(line)==34 and len(tf)==12
    line_ok=sum(x["line_positive_sequence_equivalence"] for x in line)
    tf_r=sum(x["series_r_match"] for x in tf)
    tf_x=sum(x["series_x_match"] for x in tf)
    tf_tap=sum(x["tap_match"] for x in tf)
    tf_vbase=sum(x["winding_voltage_base_match"] for x in tf)
    report={
      "status":"PASS_NATIVE_POSITIVE_SEQUENCE_LINE_PARAMETER_AUDIT" if line_ok==34 else "PARTIAL_NATIVE_PARAMETER_EQUIVALENCE",
      "reference_source":ref["source"],"native_model":native["model"],
      "system_base":{"baseMVA":Sbase,"bus_base_kV":Vbase,"frequency_Hz":60,"Zbase_ohm":Zbase},
      "matched_topology":{"lines":34,"transformers":12,"total":46,"unmatched":0},
      "line_positive_sequence_parameter_matches":{"R":sum(x["r_match"] for x in line),"X":sum(x["x_match"] for x in line),"B":sum(x["b_match"] for x in line),"all_R_X_B":line_ok},
      "transformer_series_parameter_matches":{"R":tf_r,"X":tf_x,"tap":tf_tap,"winding_voltage_bases":tf_vbase},
      "transformer_nominal_rating_MW_distribution":sorted(set(x["native_SRated"] for x in tf)),
      "transformer_rateA_MVA_distribution":sorted(set(x["matpower_rateA_MVA"] for x in tf)),
      "branch_results":records,
      "line_thermal_limits_validated":False,
      "transformer_thermal_limits_validated":False,
      "full_network_safety_certified":False,
      "interpretation":(
       "For the native three-phase line blocks, positive-sequence quantities are reconstructed from the self/mutual "
       "parameters: R1=(R-Rm)LENGTH, X1=2*pi*f*(L-M)LENGTH, and B1=2*pi*f*(Cg+3Cl)LENGTH*Zbase. "
       "These are compared with MATPOWER case39 per-unit R/X/B. Transformer winding leakage R/X sums are checked "
       "separately from winding voltage bases and tap ratios. Even if series R/X matches, a mismatch in winding "
       "voltage bases/tap or nominal rating prevents promotion to a physically equivalent transformer. MATPOWER "
       "RATE_A remains a reference benchmark, not a validated thermal ampacity of the MathWorks model."
      )
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","system_base","matched_topology","line_positive_sequence_parameter_matches","transformer_series_parameter_matches","transformer_nominal_rating_MW_distribution","transformer_rateA_MVA_distribution")},indent=2))
    for x in tf:
      print("TF",x["native_component"],"R/X",x["series_r_match"],x["series_x_match"],
            "tap",x["native_tap_ratio_relative_to_matpower_bus_bases"],"matpower",x["matpower_tap_ratio"],
            "V",x["native_VRated1_kV"],x["native_VRated2_kV"],"rateA",x["matpower_rateA_MVA"])

if __name__=="__main__":
    main()
