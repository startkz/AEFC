#!/usr/bin/env python3
import json,pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_generator_measurement_bus_probe_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/generator_measurement_bus_probe_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
s=d["generator_bus_summary"]
assert s["sample_count"]>=2 or s["field_names"],s
report={
 "status":"PASS_GENERATOR_MEASUREMENT_BUS_RUNTIME_CAPTURE",
 "runtime_class":d["generator_bus_runtime_class"],
 "runtime_bus_summary":s,
 "full_network_safety_certified":False,
 "interpretation":"This runtime capture establishes the field names and dimensions exposed by the existing generator measurement bus. It does not establish sensor integrity or full IEEE39 measurement coverage."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":report["status"],"runtime_class":report["runtime_class"],"root_fields":s.get("field_names"),"sample_count":s.get("sample_count")},indent=2))
