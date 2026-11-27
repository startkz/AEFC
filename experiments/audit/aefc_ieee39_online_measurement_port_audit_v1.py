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
candidates=as_list(d["measurement_or_converter_candidate_blocks"])
ps=[x for x in candidates if x.get("mask_type")=="PS-Simulink\nConverter"]
sps=[x for x in candidates if x.get("mask_type")=="Simulink-PS\nConverter"]
sm=[x for x in candidates if x.get("mask_type")=="Synchronous Machine\nMeasurement"]
ps_grid=[x for x in ps if "/Grid/" in x.get("path","")]
ps_generators=[x for x in ps if "/Generators/" in x.get("path","")]
gen_angle=[x for x in ps_generators if x.get("path","").endswith("/PS-Simulink\nConverter1")]
gen_speed=[x for x in ps_generators if x.get("path","").endswith("/PS-Simulink\nConverter11")]
gen_terminal_v=[x for x in ps_generators if x.get("path","").endswith("/PS-Simulink\nConverter12")]
def signal_port_count(components):
    return sum(1 for c in as_list(components) for p in as_list(c.get("port_handles",[]))
               if p.get("field") not in ("LConn","RConn"))
bus_signal_ports=signal_port_count(d["busbar_blocks"])
line_signal_ports=signal_port_count(d["line_blocks"])
tf_signal_ports=signal_port_count(d["transformer_blocks"])
assert len(ps)==70 and len(ps_grid)==0 and len(ps_generators)==70
assert len(sps)==20 and len(sm)==60
assert len(gen_angle)==10 and len(gen_speed)==10 and len(gen_terminal_v)==10
assert bus_signal_ports==line_signal_ports==tf_signal_ports==0
report={
 "status":"PASS_NATIVE_SIGNAL_PORT_INVENTORY",
 "native_busbar_blocks":d["native_busbar_blocks"],
 "native_line_blocks":d["native_line_blocks"],
 "native_transformer_blocks":d["native_transformer_blocks"],
 "measurement_or_converter_candidate_block_count":d["measurement_or_converter_candidate_block_count"],
 "ps_simulink_converter_blocks":len(ps),
 "ps_simulink_converter_blocks_inside_grid":len(ps_grid),
 "ps_simulink_converter_blocks_inside_generators":len(ps_generators),
 "simulink_ps_converter_blocks":len(sps),
 "synchronous_machine_measurement_blocks":len(sm),
 "existing_generator_measurement_signal_candidates":{
   "rotor_angle":len(gen_angle),
   "rotor_velocity":len(gen_speed),
   "terminal_voltage":len(gen_terminal_v)
 },
 "busbar_exposed_port_handle_count":count_ports(d["busbar_blocks"]),
 "line_exposed_port_handle_count":count_ports(d["line_blocks"]),
 "transformer_exposed_port_handle_count":count_ports(d["transformer_blocks"]),
 "busbar_signal_output_port_count":bus_signal_ports,
 "line_signal_output_port_count":line_signal_ports,
 "transformer_signal_output_port_count":tf_signal_ports,
 "controller_exposed_port_handle_count":len(as_list(d["controller"].get("port_handles",[]))),
 "online_physical_measurement_channels":4,
 "online_physical_measurement_type":"four generator rotor-speed channels only",
 "generator_angle_speed_terminal_voltage_candidates_routed_to_controller":False,
 "all_bus_voltage_online_measurement_channels":0,
 "all_line_terminal_current_online_measurement_channels":0,
 "all_transformer_winding_current_online_measurement_channels":0,
 "trusted_online_sensor_integrity_verified":False,
 "sensor_error_bounds_verified":False,
 "full_network_safety_certified":False,
 "interpretation":(
   "The model already exposes ten generator rotor-angle, ten rotor-velocity and ten generator-terminal-voltage "
   "signal candidates through generator-local PS-Simulink converters. Only four rotor-speed channels are routed "
   "to AEFCNativeController. No PS-Simulink converter is present in the Grid subsystem; Busbar, line and "
   "transformer blocks expose only conserving ports and no signal output ports. Therefore the 39-bus voltage "
   "and branch-current Simscape Series remain offline logs, not online measurements. Adding explicit network "
   "voltage/current sensors and routing their outputs to a separate safety monitor is the next required step. "
   "No sensor integrity, error bound, or full-grid safety claim is established."
 )
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
