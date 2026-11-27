#!/usr/bin/env python3
import json,pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_generator_measurement_bus_audit_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/generator_measurement_bus_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
assert d["generator_subsystem"]["path"].endswith("/Generators")
assert d["measurements_subsystem"]["path"].endswith("/Measurements")
assert d["generator_descendant_block_count"]>0
assert d["measurements_descendant_block_count"]>0
assert d["generator_measurement_bus_routed_to_aefc_controller"] is False
def as_list(x):
    if x is None: return []
    if isinstance(x,list): return x
    if isinstance(x,dict): return [x]
    return []
def pmap(x):
    q=as_list(x.get("dialog_parameters",[]))
    return {z.get("name"):z.get("value") for z in q}
meas_blocks=as_list(d["measurements_subsystem_blocks"])
bus_elements=[{"name":x.get("name"),"path":x.get("path"),"block_type":x.get("block_type"),"params":pmap(x)} for x in meas_blocks if "Bus Element" in x.get("name","")]
mux_blocks=[{"name":x.get("name"),"path":x.get("path"),"params":pmap(x),"port_connectivity":x.get("port_connectivity")} for x in meas_blocks if x.get("block_type")=="Mux"]
gen_blocks=as_list(d["generator_measurement_related_blocks"])
bus_creators=[{"name":x.get("name"),"path":x.get("path"),"params":pmap(x),"port_connectivity":x.get("port_connectivity")} for x in gen_blocks if "Bus Creator" in x.get("name","")]
report={
 "status":"PASS_GENERATOR_MEASUREMENT_BUS_INVENTORY",
 "generator_descendant_block_count":d["generator_descendant_block_count"],
 "measurements_descendant_block_count":d["measurements_descendant_block_count"],
 "generator_subsystem_ports":d["generator_subsystem"]["port_handles"],
 "measurements_subsystem_ports":d["measurements_subsystem"]["port_handles"],
 "measurements_subsystem_is_sink_only":d["measurements_subsystem_is_sink_only"],
 "measurements_bus_element_count":len(bus_elements),
 "measurements_bus_elements":bus_elements,
 "measurements_mux_blocks":mux_blocks,
 "generator_bus_creator_count":len(bus_creators),
 "generator_bus_creators":bus_creators,
 "generator_measurement_bus_routed_to_aefc_controller":False,
 "current_controller_physical_inputs":4,
 "full_network_safety_certified":False,
 "interpretation":"The Generators-to-Measurements route is an existing model-level measurement bus, but it is not routed to AEFCNativeController. Its signal contents and any sensor-trust properties must be verified before use in a safety monitor."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
