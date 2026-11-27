#!/usr/bin/env python3
import json, pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_bus16_port_current_fault_probe_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
assert d["fault_start_s"]==5.0 and d["fault_duration_s"]==0.1
bus16=[x for x in d["bus_port_current_series"] if x["bus_section"]=="Bus16_1"]
assert len(bus16)==4 and sorted(x["port_index"] for x in bus16)==[1,2,3,4]
assert len(d["line_terminal_current_series"])==2
assert len(d["fault_current_series"])==1
for x in bus16+d["line_terminal_current_series"]+d["fault_current_series"]:
    assert x["unit"]=="A" and len(x["time_s"])>=2
    assert len(x["values_real"])==len(x["time_s"])
out={"status":"PASS_BUS16_PORT_CURRENT_CAPTURE","bus16_1_current_series":len(bus16),
     "line_terminal_current_vectors":2,"fault_current_vectors":1,
     "full_network_safety_certified":False,"thermal_limits_validated":False}
pathlib.Path("results/ieee39_safety_mapping/bus16_port_current_fault_probe_audit_v1.json").write_text(
    json.dumps(out,indent=2)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2))
