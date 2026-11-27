#!/usr/bin/env python3
import json,pathlib,subprocess,sys
out=pathlib.Path("results/ieee39_safety_mapping/fullstate_gate_recheck_v1.json")
out.parent.mkdir(parents=True,exist_ok=True)
p=subprocess.run([sys.executable,"analysis/audit_ieee39_fullstate_gate.py",
 "--registry","configs/ieee39_fullstate_certification_requirements.json",
 "--mapping","results/ieee39_r2024b/interface_mapping.json"],
 check=True,capture_output=True,text=True)
d=json.loads(p.stdout)
assert d["status"]=="BLOCKED",d
assert d["full_network_certified"] is False,d
blockers=d["blocking_requirements"]
required=[
 "NO_FULLSTATE_ONLINE_OBSERVER_COVERAGE_PROOF",
 "NO_OBSERVER_ERROR_BOUND_PROOF",
 "NO_ALL_STATE_MEASUREMENT_MAP",
 "NO_VALIDATED_FULL_NETWORK_SAMPLED_REACHABLE_TUBE",
 "NO_FULL_NONLINEAR_INTERSAMPLE_REACHABILITY",
 "NO_INDEPENDENT_SIX_METHOD_RECOVERY_HOLDOUT"
]
for x in required:
 assert x in blockers,x
out.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({"status":d["status"],"blocking_requirement_count":len(blockers),
 "required_blockers_present":required,"report_path":str(out)},indent=2,ensure_ascii=False))
