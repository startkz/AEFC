#!/usr/bin/env python3
"""Independently reclassify original official IEEE39 Simscape log node names.

Do NOT call all '/Terminal_voltage/' conversion variants independent buses
or '/ic_reactive_power_generated' machine initialization a branch flow.
Unique 10 generator terminals (buses 30-39) != complete 39-bus network.
"""
import argparse
import json
import re
from pathlib import Path


def reclassify(original:Path,out:Path):
    data=json.loads(original.read_text())
    assert data["simscape_log_available"] is True
    assert data["status"]=="OFFLINE_SIMSCAPE_LOG_INVENTORY_ONLY"
    assert data["number_of_nodes_inspected"]==22413
    assert data["truncated"] is False
    raw=data["candidate_node_paths"]
    pattern_voltage=re.compile(
        r"^IEEE39BusSystem/Generators/(Gen\d+Bus\d+)/Terminal_voltage$")
    pattern_angle=re.compile(
        r"^IEEE39BusSystem/Generators/(Gen\d+Bus\d+)/Rotor_electrical_angle$")
    raw_q=re.compile(
        r"^IEEE39BusSystem/Generators/(Gen\d+Bus\d+)/Gen\d+/ic_reactive_power_generated$")
    def get(pattern):
        return {m.group(1):p["path"] for p in raw
                if (m:=pattern.fullmatch(p["path"]))}
    volt=get(pattern_voltage);ang=get(pattern_angle);reactive=get(raw_q)
    assert len(volt)==len(ang)==len(reactive)==10
    assert set(volt)==set(ang)==set(reactive)
    busnumbers={}
    for gen in volt:
        m=re.fullmatch(r"Gen(\d+)Bus(\d+)",gen)
        assert m
        busnumbers[gen]=int(m.group(2))
    assert set(busnumbers.values())==set(range(30,40))
    categories=data["potential_measurement_node_counts"]
    assert categories["bus_voltage"]==70
    assert categories["rotor_angle"]==30
    assert categories["branch_power"]==10
    assert categories["branch_current"]==0
    result=dict(source_status=data["status"],
      original_simscape_nodes_inspected=data["number_of_nodes_inspected"],
      original_unclassified_name_matches=categories,
      unique_generator_terminal_voltage_signal_candidates=len(volt),
      unique_generator_rotor_angle_signal_candidates=len(ang),
      unique_generator_reactive_power_INITIALIZATION_parameters=len(reactive),
      generator_terminal_bus_ids=sorted(set(busnumbers.values())),
      generator_terminal_voltage_offline_log_paths=volt,
      generator_rotor_angle_offline_log_paths=ang,
      generator_reactive_power_initialization_parameter_paths=reactive,
      original_70_voltage_related_node_entries_not_70_distinct_bus_voltages=True,
      original_30_angle_related_entries_not_30_distinct_rotor_angles=True,
      original_10_power_entries_are_generator_reactive_power_parameters_NOT_branch_flows=True,
      other_29_bus_voltage_online_paths_verified=0,
      full_39_bus_voltage_online_paths_verified=0,
      branch_current_online_sensor_paths_verified=0,
      rotor_angle_online_sensor_integrity_verified=0,
      complete_online_CPS_state_observability_proven=False,
      complete_nonlinear_DAE_coverage_proven=False,
      full_network_continuous_reachable_tube_proven=False,
      review_status="REAL_GENERATOR_PHYSICAL_LOG_EXISTS_BUT_FULL_GRID_COVERAGE_UNPROVEN")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:result[k] for k in (
      "unique_generator_terminal_voltage_signal_candidates",
      "unique_generator_rotor_angle_signal_candidates",
      "unique_generator_reactive_power_INITIALIZATION_parameters",
      "generator_terminal_bus_ids",
      "other_29_bus_voltage_online_paths_verified",
      "review_status")},indent=2,ensure_ascii=False))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--original",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    reclassify(a.original,a.output)
