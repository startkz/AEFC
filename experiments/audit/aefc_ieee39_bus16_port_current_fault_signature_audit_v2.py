#!/usr/bin/env python3
import json, pathlib
import numpy as np

root=pathlib.Path("artifacts/bus16_fault_probe")
hits=list(root.rglob("native_ieee39_bus16_port_current_fault_probe_v1.json"))
assert len(hits)==1, f"expected one raw Bus16 fault probe, got {len(hits)}"
d=json.loads(hits[0].read_text(encoding="utf-8"))
bus=[x for x in d["bus_port_current_series"] if x["bus_section"]=="Bus16_1"]
assert len(bus)==4
by_i={int(x["port_index"]):x for x in bus}
assert set(by_i)=={1,2,3,4}
line=d["line_terminal_current_series"]
assert len(line)==2
line_by_terminal={int(x["terminal"]):x for x in line}
assert set(line_by_terminal)=={1,2}
fault=d["fault_current_series"]
assert isinstance(fault,dict), "fault_current_series must be a single series object"

def arr(x): return np.asarray(x["values_real"],dtype=float)
t=np.asarray(by_i[2]["time_s"],dtype=float)
line1=arr(line_by_terminal[1])
fault_i=arr(fault)
assert line1.shape==fault_i.shape==arr(by_i[2]).shape
pre=(t>=4.5)&(t<5.0)
fault_mask=(t>=5.0)&(t<=5.1)
assert pre.sum()>0 and fault_mask.sum()>0

rows=[]
for idx,x in by_i.items():
    cur=arr(x)
    pre_ref=-line1[pre]
    fault_ref=-(line1[fault_mask]+fault_i[fault_mask])
    pre_err=float(np.linalg.norm(cur[pre]-pre_ref)/max(np.linalg.norm(cur[pre]),np.linalg.norm(pre_ref),1e-12))
    fault_err=float(np.linalg.norm(cur[fault_mask]-fault_ref)/max(np.linalg.norm(cur[fault_mask]),np.linalg.norm(fault_ref),1e-12))
    fault_peak=float(np.max(np.abs(cur[fault_mask])))
    rows.append({"current_variable":f"I{idx}","prefault_line_terminal_residual":pre_err,
                 "fault_line_plus_fault_residual":fault_err,"fault_window_peak_A":fault_peak})
rows.sort(key=lambda x:x["fault_line_plus_fault_residual"])
best=rows[0]
assert best["current_variable"]=="I2", rows
assert best["fault_line_plus_fault_residual"]<1e-8, best
assert best["prefault_line_terminal_residual"]<1e-3, best

fault_peak=float(np.max(np.abs(fault_i[fault_mask])))
summary={
 "status":"PASS_BUS16_RCONN1_CURRENT_SUM",
 "physical_port":"Bus16_1/RConn1",
 "mapped_current_variable":"I2",
 "prefault_relation":"I2 approximately equals -B16-B17 phase_splitter1 current (small inactive-fault leakage)",
 "fault_relation":"I2 = -(B16-B17 phase_splitter1 current + three-phase fault current)",
 "prefault_normalized_residual":best["prefault_line_terminal_residual"],
 "fault_normalized_residual":best["fault_line_plus_fault_residual"],
 "fault_current_peak_A":fault_peak,
 "bus16_1_I2_fault_window_peak_A":best["fault_window_peak_A"],
 "all_bus16_1_port_candidates":rows,
 "full_network_safety_certified":False,
 "branch_thermal_limits_validated":False,
 "interpretation":"This validates the composite current sum for one native Bus16 fault episode; it is not a thermal or full-network safety certificate."
}
out=pathlib.Path("results/ieee39_safety_mapping/bus16_port_current_fault_signature_audit_v2.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,indent=2))
