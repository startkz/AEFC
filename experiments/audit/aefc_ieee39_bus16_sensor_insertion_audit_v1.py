#!/usr/bin/env python3
from __future__ import annotations
import json,math,pathlib,itertools
import numpy as np

ROOT=pathlib.Path(".")
PILOT=ROOT/"results/ieee39_safety_mapping/native_ieee39_bus16_sensor_insertion_pilot_v1.json"
BASE=ROOT/"artifacts/confirmatory"
OUT=ROOT/"results/ieee39_safety_mapping/bus16_sensor_insertion_audit_v1.json"

def find_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return hits[0]

def interp_rows(row,t):
    tt=np.asarray(row["time_s"],float)
    vv=np.asarray(row["values_real"],float)
    if vv.ndim==1:vv=vv[:,None]
    if vv.shape[0]!=len(tt) and vv.shape[1]==len(tt):vv=vv.T
    return np.column_stack([np.interp(t,tt,vv[:,k]) for k in range(vv.shape[1])])

def best_current_match(sensor,offline):
    ts=np.asarray(sensor["time_s"],float)
    vs=np.asarray(sensor["values_real"],float)
    if vs.ndim==1:vs=vs[:,None]
    off=interp_rows(offline,ts)
    assert vs.shape[1]==off.shape[1]==3,(vs.shape,off.shape)
    best=None
    for perm in itertools.permutations(range(3)):
        for sign in (-1,1):
            err=vs-sign*off[:,perm]
            score=float(np.max(np.abs(err))/max(float(np.max(np.abs(off))),1e-12))
            if best is None or score<best["normalized_max_abs_error"]:
                best={"permutation":list(perm),"sign":sign,"normalized_max_abs_error":score,
                      "max_abs_error_A":float(np.max(np.abs(err)))}
    return best

def sensor_voltage_envelope(sensor,bus):
    ts=np.asarray(sensor["time_s"],float)
    vv=np.asarray(sensor["values_real"],float)
    if vv.ndim==1:vv=vv[:,None]
    if vv.shape[1]==3:
        mag=np.sqrt(np.mean(vv**2,axis=1))
    else:
        mag=np.sqrt(np.mean(vv**2,axis=1))
    tb=np.asarray(bus["time_s"],float)
    vb=np.asarray(bus["values_real"],float)
    if vb.ndim>1:vb=np.sqrt(np.mean(vb**2,axis=1))
    pre_s=mag[ts<4.5];pre_b=vb[tb<4.5]
    assert len(pre_s)>0 and len(pre_b)>0
    sn=mag/float(np.mean(pre_s));bn=vb/float(np.mean(pre_b))
    sn_at_bus=np.interp(tb,ts,sn)
    mask=(tb>=0.1)&(tb<=8.0)
    err=np.abs(sn_at_bus[mask]-bn[mask])
    return {"max_abs_relative_envelope_error":float(np.max(err)),
            "mean_abs_relative_envelope_error":float(np.mean(err)),
            "sensor_voltage_channels":int(vv.shape[1]),
            "bus_vt_unit":bus["unit"]}

def main():
    d=json.loads(PILOT.read_text(encoding="utf-8"))
    baseline_dir=BASE/"results/ieee39_fault_recovery_r1/confirmatory_v1/AEFC-Full"
    baseline_rows=[json.loads(x) for x in find_unique(baseline_dir,"seed_80.jsonl").read_text().splitlines() if x.strip()]
    baseline_bus=json.loads(find_unique(baseline_dir,"seed_80.bus-map.json").read_text())
    baseline_speed=json.loads(find_unique(baseline_dir,"seed_80.generator-speed.json").read_text())
    tbase=np.array([x["time"] for x in baseline_rows],float)
    assert len(tbase)==481
    bus_rows={x["bus_section"]:x for x in d["bus_voltage_series"]}
    speed_rows={x["generator"]:x for x in d["generator_speed_series"]}
    assert len(bus_rows)==41 and len(speed_rows)==10
    # Confirm the native Simscape monitor trajectories are unchanged by the
    # passive sensor insertion at the 60-Hz recovery-monitor sample times.
    bus_diffs=[]
    for i,m in enumerate(baseline_bus):
        section=m["path"].split("/Grid/")[-1].split("/Vt/")[0]
        assert section in bus_rows,section
        sampled=interp_rows(bus_rows[section],tbase).reshape(len(tbase),-1)[:,0]
        ref=np.array([x["bus_vt_sections"][i] for x in baseline_rows],float)
        bus_diffs.append(float(np.max(np.abs(sampled-ref))))
    speed_diffs=[]
    base_speed=np.asarray(baseline_speed["generator_speed_pu"],float)
    assert base_speed.shape==(481,10),base_speed.shape
    for g in range(1,11):
        name=next(x for x in speed_rows if x.startswith(f"Gen{g}@"))
        sampled=interp_rows(speed_rows[name],tbase).reshape(len(tbase),-1)[:,0]
        speed_diffs.append(float(np.max(np.abs(sampled-base_speed[:,g-1]))))
    # Sensor-current output must reproduce the native line terminal current.
    line={x["terminal"]:x for x in d["line_terminal_current_series"]}
    assert set(line)=={1,2}
    current_match=best_current_match(d["sensor_current_series"],line[1])
    # Line-voltage sensor envelope is checked against the native Bus16_1 Vt.
    bus16=bus_rows["Bus16_1"]
    voltage_match=sensor_voltage_envelope(d["sensor_voltage_series"],bus16)
    max_bus=max(bus_diffs);max_speed=max(speed_diffs)
    report={
      "status":"PASS_BUS16_SENSOR_INSERTION_AND_SIGNAL_RECONCILIATION",
      "source_run":"native sensor insertion pilot, seed 80",
      "baseline_run_id":45924335524,
      "bus_voltage_sections_compared":len(bus_diffs),
      "generator_speed_channels_compared":len(speed_diffs),
      "max_bus_voltage_trajectory_abs_difference_pu":max_bus,
      "max_generator_speed_trajectory_abs_difference_pu":max_speed,
      "current_sensor_to_native_line_current":current_match,
      "voltage_sensor_to_native_bus_vt_envelope":voltage_match,
      "plant_trajectory_unchanged":max_bus<=1e-5 and max_speed<=1e-5,
      "current_sensor_matches_native_line_current":current_match["normalized_max_abs_error"]<=1e-3,
      "voltage_sensor_envelope_matches_bus_vt":voltage_match["max_abs_relative_envelope_error"]<=0.02,
      "full_network_sensor_coverage_complete":False,
      "sensor_integrity_and_error_bounds_verified":False,
      "full_network_safety_certified":False,
      "interpretation":"This validates one Bus16_1 voltage sensor and one B16-B17 terminal current sensor against native simulator logs and checks that passive instrumentation does not measurably perturb the no-sensor plant trajectory. It is not a full-grid measurement or safety certificate."
    }
    assert report["plant_trajectory_unchanged"],report
    assert report["current_sensor_matches_native_line_current"],report
    assert report["voltage_sensor_envelope_matches_bus_vt"],report
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
