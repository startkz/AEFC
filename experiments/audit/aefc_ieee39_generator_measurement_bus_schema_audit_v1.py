#!/usr/bin/env python3
import json,pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_generator_measurement_bus_schema_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/generator_measurement_bus_schema_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
records=d["blocks"]
assert len(records)>=20
report={
 "status":"PASS_GENERATOR_BUS_SCHEMA_EXPORT",
 "block_count":len(records),
 "blocks":[{"path":x.get("path"),"name":x.get("name"),"block_type":x.get("block_type"),
            "mask_names":x.get("mask_names"),"mask_values":x.get("mask_values"),
            "dialog_parameters":x.get("dialog_parameters")} for x in records],
 "full_network_safety_certified":False,
 "interpretation":"Bus Creator/In Bus Element names describe model-generated generator signals. They do not establish trusted sensor integrity or full-grid measurement coverage."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":report["status"],"block_count":report["block_count"]},indent=2))
