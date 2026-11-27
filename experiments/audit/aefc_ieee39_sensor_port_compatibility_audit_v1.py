#!/usr/bin/env python3
import json,pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_ieee39_sensor_port_compatibility_probe_v1.json")
o=pathlib.Path("results/ieee39_safety_mapping/sensor_port_compatibility_audit_v1.json")
d=json.loads(p.read_text(encoding="utf-8"))
results=[]
for x in d["sensor_candidates"]:
 tries=x.get("candidate_ps_connections",[])
 if isinstance(tries,dict):tries=[tries]
 successes=[t for t in tries if t.get("success")]
 results.append({
  "library_path":x["library_path"],
  "block_added":x["block_added"],
  "mask_type":x.get("mask_type"),
  "connected_ps_port":x.get("connected_ps_port"),
  "successful_ps_port_candidates":successes,
  "port_handles":x.get("port_handles",[]),
  "connection_error":x.get("connection_error","")
 })
assert len(results)==6
assert any(x["successful_ps_port_candidates"] for x in results), "No sensor PS outputs connected to PS-Simulink Converter"
report={
 "status":"PASS_SENSOR_PS_PORT_COMPATIBILITY_PROBE",
 "sensor_candidates":results,
 "full_network_safety_certified":False,
 "interpretation":"The identified physical-signal ports can be connected to a PS-Simulink Converter. This is a port compatibility test only; actual network sensor insertion, measurement calibration, error bounds and safety certification remain outstanding."
}
o.parent.mkdir(parents=True,exist_ok=True)
o.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":report["status"],"candidates":[{"path":x["library_path"],"connected_ps_port":x["connected_ps_port"]} for x in results]},indent=2))
