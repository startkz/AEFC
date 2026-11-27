#!/usr/bin/env python3
import json,pathlib,collections
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_branch_parameter_inventory_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/branch_parameter_inventory_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
assert d["line_component_count"]==34
assert d["transformer_component_count"]==12
def summarize(items):
 out=[]
 for x in items:
  params=x.get("dialog_parameters",[])
  if isinstance(params,dict): params=[params]
  out.append({
   "component":x["name"],"mask_type":x["mask_type"],
   "reference_block":x["reference_block"],
   "mask_parameter_count":len(x.get("mask_names",[])),
   "dialog_parameter_count":len(params),
   "parameter_names":[q.get("name") for q in params],
   "parameter_values":{q.get("name"):q.get("value") for q in params}
  })
 return out
report={
 "status":"PASS_NATIVE_BRANCH_PARAMETER_EXPORT",
 "line_components":summarize(d["line_components"]),
 "transformer_components":summarize(d["transformer_components"]),
 "model_nominal_frequency_hz":d["model_nominal_frequency_hz"],
 "model_base_mva":d["model_base_mva"],
 "model_base_voltage_kv":d["model_base_voltage_kv"],
 "parameter_equivalence_verified":False,
 "thermal_limit_verified":False,
 "interpretation":"This is a parameter export for independent comparison. It does not itself establish equivalence to MATPOWER case39 or validate thermal ratings."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":report["status"],"lines":len(report["line_components"]),"transformers":len(report["transformer_components"]),"line_parameter_name_examples":report["line_components"][:2],"transformer_parameter_name_examples":report["transformer_components"][:2]},indent=2))
