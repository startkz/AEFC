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
report={
 "status":"PASS_GENERATOR_MEASUREMENT_BUS_INVENTORY",
 "generator_descendant_block_count":d["generator_descendant_block_count"],
 "measurements_descendant_block_count":d["measurements_descendant_block_count"],
 "generator_subsystem_ports":d["generator_subsystem"]["port_handles"],
 "measurements_subsystem_ports":d["measurements_subsystem"]["port_handles"],
 "measurements_subsystem_is_sink_only":d["measurements_subsystem_is_sink_only"],
 "generator_measurement_bus_routed_to_aefc_controller":False,
 "current_controller_physical_inputs":4,
 "full_network_safety_certified":False,
 "interpretation":"The Generators-to-Measurements route is an existing model-level measurement bus, but it is not routed to AEFCNativeController. Its signal contents and any sensor-trust properties must be verified before use in a safety monitor."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
