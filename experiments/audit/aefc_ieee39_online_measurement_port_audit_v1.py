#!/usr/bin/env python3
"""Check completeness and claim boundaries of native IEEE39 signal-port inventory."""
import json
import pathlib

src=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_online_measurement_port_audit_v1.json")
out=pathlib.Path("results/ieee39_safety_mapping/online_measurement_port_audit_v1.json")
d=json.loads(src.read_text(encoding="utf-8"))
assert d["native_busbar_blocks"]==41, d["native_busbar_blocks"]
assert d["native_line_blocks"]==34, d["native_line_blocks"]
assert d["native_transformer_blocks"]==12, d["native_transformer_blocks"]
assert d["current_online_controller_physical_inputs"]==4
assert d["current_online_controller_total_top_level_inputs"]==2
assert d["bus_voltage_simscape_log_is_online_signal"] is False
assert d["line_terminal_current_simscape_log_is_online_signal"] is False
assert d["transformer_winding_current_simscape_log_is_online_signal"] is False
assert d["trusted_online_sensor_integrity_verified"] is False
assert d["sensor_error_bounds_verified"] is False
assert d["full_network_safety_certified"] is False

def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []

def count_ports(x):
    return sum(len(as_list(y.get("port_handles",[]))) for y in as_list(x))
report={
 "status":"PASS_NATIVE_SIGNAL_PORT_INVENTORY",
 "native_busbar_blocks":d["native_busbar_blocks"],
 "native_line_blocks":d["native_line_blocks"],
 "native_transformer_blocks":d["native_transformer_blocks"],
 "measurement_or_converter_candidate_block_count":d["measurement_or_converter_candidate_block_count"],
 "busbar_exposed_port_handle_count":count_ports(d["busbar_blocks"]),
 "line_exposed_port_handle_count":count_ports(d["line_blocks"]),
 "transformer_exposed_port_handle_count":count_ports(d["transformer_blocks"]),
 "controller_exposed_port_handle_count":len(as_list(d["controller"].get("port_handles",[]))),
 "online_physical_measurement_channels":4,
 "trusted_online_sensor_integrity_verified":False,
 "sensor_error_bounds_verified":False,
 "full_network_safety_certified":False,
 "interpretation":(
   "This confirms the existing native model's block-level signal-port inventory and the four physical "
   "measurement channels currently routed to AEFCNativeController. Logged Busbar Vt and Simscape current "
   "Series are not treated as online signals unless an actual signal port and routed measurement path are "
   "identified. No sensor integrity, error bound, or full-grid safety claim is established."
 )
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
