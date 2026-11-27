#!/usr/bin/env python3
import json,pathlib,collections
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_sensor_library_inventory_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/sensor_library_inventory_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
arr=d["candidate_blocks"]
def ports(x):
 v=x.get("port_handles",[])
 if isinstance(v,dict):return [v]
 return v if isinstance(v,list) else []
def searchable(x):
 return " ".join(str(x.get(k,"")) for k in ("name","mask_type","reference_block","path")).lower()
voltage=[x for x in arr if "voltage" in searchable(x) and "sensor" in searchable(x)]
current=[x for x in arr if "current" in searchable(x) and "sensor" in searchable(x)]
three_phase=[x for x in arr if "three-phase" in searchable(x) or "three phase" in searchable(x)]
signal_candidates=[]
for x in arr:
 fs={p.get("field") for p in ports(x)}
 if fs & {"PS","PSOut","Outport","Out"}:
  signal_candidates.append(x)
report={
 "status":"PASS_SENSOR_LIBRARY_INVENTORY",
 "candidate_block_count":len(arr),
 "voltage_sensor_candidate_count":len(voltage),
 "current_sensor_candidate_count":len(current),
 "three_phase_measurement_candidate_count":len(three_phase),
 "physical_signal_output_candidate_count":len(signal_candidates),
 "voltage_sensor_candidates":[{"path":x["path"],"mask_type":x["mask_type"],"ports":ports(x)} for x in voltage],
 "current_sensor_candidates":[{"path":x["path"],"mask_type":x["mask_type"],"ports":ports(x)} for x in current],
 "three_phase_candidates":[{"path":x["path"],"mask_type":x["mask_type"],"ports":ports(x)} for x in three_phase],
 "full_network_safety_certified":False,
 "interpretation":"This is a library discovery result. Candidate selection still requires compatibility tests against the native three-phase conserving ports and proof that the output is a physical-signal measurement, not a Specialized Power Systems port."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:report[k] for k in ("status","candidate_block_count","voltage_sensor_candidate_count","current_sensor_candidate_count","three_phase_measurement_candidate_count","physical_signal_output_candidate_count")},indent=2))
