#!/usr/bin/env python3
import csv, json, math, pathlib, sys
ROOT = pathlib.Path(sys.argv[1])
SCENARIOS = ("hold", "rate_limited", "step")
errors, summaries = [], {}
def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
for scenario in SCENARIOS:
    folder = ROOT / scenario
    summary_path = folder / "dynamic_summary.json"
    required = ["frequency_trace.csv", "governor_actuator_trace.csv",
                "feeder_pickup_actuator_trace.csv", "protection_events.csv"]
    if not summary_path.is_file():
        errors.append(f"{scenario}: missing dynamic_summary.json")
        continue
    missing = [name for name in required if not (folder / name).is_file()]
    if missing:
        errors.append(f"{scenario}: missing {missing}")
        continue
    s = json.loads(summary_path.read_text(encoding="utf-8"))
    summaries[scenario] = s
    freq, gov, act, events = [read_csv(folder / n) for n in required]
    if not s.get("solver_success"): errors.append(f"{scenario}: solver unsuccessful")
    if len(freq) < 1000 or len(gov) < 1000 or len(act) < 1000:
        errors.append(f"{scenario}: incomplete time series")
    if s.get("machine_count") != 10 or s.get("governor_count") != 9:
        errors.append(f"{scenario}: expected 10 machines and 9 governors")
    for key in ("coi_frequency_hz", "coi_frequency_deviation_hz", "coi_rocof_hz_per_s"):
        if key not in freq[0]: errors.append(f"{scenario}: missing {key}")
    for row in freq:
        for key in ("coi_frequency_hz", "coi_frequency_deviation_hz", "coi_rocof_hz_per_s"):
            if not math.isfinite(float(row[key])):
                errors.append(f"{scenario}: non-finite {key}"); break
    valve = [float(r["valve_position_pu"]) for r in gov]
    if min(valve) < -1e-4 or max(valve) > 1.0001:
        errors.append(f"{scenario}: TGOV1 valve outside [0,1]")
    if s.get("measured_max_governor_valve_rate_pu_per_s", 1e9) > 0.115:
        errors.append(f"{scenario}: TGOV1 valve slew limit violated")
    names = [r["event"] for r in events]
    if "three_phase_fault" not in names or "protection_line_trip" not in names:
        errors.append(f"{scenario}: missing fault or protection event")
    else:
        fault = next(float(r["time_s"]) for r in events if r["event"] == "three_phase_fault")
        trip = next(float(r["time_s"]) for r in events if r["event"] == "protection_line_trip")
        if abs(fault-.10)>1e-8 or abs(trip-.20)>1e-8 or abs(trip-fault-.10)>1e-8:
            errors.append(f"{scenario}: protection timing mismatch")
    applied = [float(r["applied_multiplier"]) for r in act]
    rates = [abs(float(r["actuator_rate_pu_per_s"])) for r in act]
    if min(applied)<.99999 or max(applied)>1.10001:
        errors.append(f"{scenario}: feeder actuator outside [1.0,1.1]")
    if scenario=="rate_limited" and max(rates)>.0201:
        errors.append("rate_limited: feeder pickup slew limit violated")
    if scenario=="hold" and max(rates)>1e-8:
        errors.append("hold: feeder actuator should remain fixed")
    if scenario=="step" and max(rates)<1.0:
        errors.append("step: unconstrained diagnostic did not step")
    if scenario=="rate_limited" and abs(applied[-1]-1.10)>1e-5:
        errors.append("rate_limited: did not reach 1.10 pu")
report = {"study":"IEEE39 dynamic transient evidence audit",
          "scenarios":list(summaries), "valid_scenarios":len(summaries),
          "errors":errors, "valid":not errors,
          "interpretation":"Checks trace completeness, frequency/ROCOF, TGOV1 valve limits, feeder actuator envelope, and scheduled protection-event records. Does not establish field-hardware validation or inverse-time relay behavior."}
(ROOT/"dynamic_audit_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
if errors: raise SystemExit(2)
