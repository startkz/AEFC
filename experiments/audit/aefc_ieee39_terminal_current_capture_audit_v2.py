#!/usr/bin/env python3
import json, pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_bus_port_terminal_current_capture_v2.json")
d=json.loads(p.read_text(encoding="utf-8"))
assert d["bus_port_current_count"]==len(d["bus_port_current_series"])==123
assert d["line_terminal_current_count"]==len(d["line_terminal_current_series"])==68
assert d["line_component_count"]==34
assert d["transformer_winding_current_count"]==len(d["transformer_winding_current_series"])==24
assert d["transformer_component_count"]==12
assert d["physical_bus_sections"]==41 and d["logical_bus_count"]==39
for x in d["bus_port_current_series"]+d["line_terminal_current_series"]+d["transformer_winding_current_series"]:
    assert x["unit"]=="A" and len(x["time_s"])>=2
    assert len(x["values_real"])==len(x["time_s"])
    assert len(x["values_imag"])==len(x["time_s"])
for x in d["line_terminal_current_series"]+d["transformer_winding_current_series"]:
    assert len(x["values_real"][0])==3
out={
 "status":"PASS_TERMINAL_CURRENT_CAPTURE",
 "bus_port_current_series":123,
 "line_terminal_current_vectors":68,
 "line_components":34,
 "transformer_winding_current_vectors":24,
 "transformer_components":12,
 "physical_bus_sections":41,
 "logical_buses":39,
 "full_network_safety_certified":False,
 "online_sensor_integrity_verified":False,
 "branch_thermal_limits_validated":False
}
pathlib.Path("results/ieee39_safety_mapping/terminal_current_capture_audit_v2.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2))
