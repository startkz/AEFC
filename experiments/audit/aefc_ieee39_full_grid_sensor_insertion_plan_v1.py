#!/usr/bin/env python3
"""Build a topology-grounded insertion plan for native IEEE39 voltage/current sensors."""
from __future__ import annotations
import json,pathlib
ROOT=pathlib.Path(".")
BUSMAP_ROOT=ROOT/"artifacts/busbar_component_map"
CURMAP_ROOT=ROOT/"artifacts/current_variable_map"
OUT=ROOT/"results/ieee39_safety_mapping/full_grid_sensor_insertion_plan_v1.json"

def load_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return json.loads(hits[0].read_text(encoding="utf-8"))

def bus_key(bus,port):
    return (bus,port)

def main():
    bm=load_unique(BUSMAP_ROOT,"native_busbar_port_component_map_v2.json")
    cm=load_unique(CURMAP_ROOT,"native_ieee39_bus_port_current_variable_map_v2.json")
    mappings=bm["busbar_port_mappings"]
    by_port={}
    for x in mappings:
        name=x["bus_block"].split("/")[-1]
        port=f'{x["bus_port_kind"]}{x["bus_port_index"]}'
        by_port[bus_key(name,port)]=x

    # One shunt voltage sensor per physical busbar section. Prefer a single-
    # component port so the voltage tap does not sit on a split/fault composite.
    buses=sorted({x["bus_block"].split("/")[-1] for x in mappings},
                 key=lambda n:(int(n.split("_")[0][3:]),n))
    voltage=[]
    for bus in buses:
        rows=[x for x in mappings if x["bus_block"].endswith("/"+bus)]
        unique=[x for x in rows if x["connected_port_count"]==1]
        chosen=(unique or rows)[0]
        voltage.append({
          "bus_section":bus,
          "logical_bus":chosen["logical_bus"],
          "bus_port":f'{chosen["bus_port_kind"]}{chosen["bus_port_index"]}',
          "connected_component":chosen["connected_ports"][0]["block_name"] if chosen["connected_ports"] else None,
          "connected_port_count":chosen["connected_port_count"],
          "selection":"single-component port" if unique else "fallback composite port",
          "sensor":"Line Voltage Sensor (Three-Phase)",
          "sensor_conserving_port":"LConn1",
          "sensor_ps_output":"RConn1"
        })
    assert len(voltage)==41 and len(set(x["bus_section"] for x in voltage))==41

    # Deduplicate terminal signatures to the 68 physical line component ports.
    line_groups={}
    for x in cm["line_terminal_signature_checks"]:
        key=(x["component"],x["component_port"])
        line_groups.setdefault(key,[]).append(x)
    assert len(line_groups)==68,(len(line_groups),len(cm["line_terminal_signature_checks"]))
    line_targets=[]
    for (component,component_port),rows in sorted(line_groups.items()):
        x=rows[0]
        composite=any(z["multi_component_bus_port"] for z in rows)
        if component=="B16 to B17" and component_port=="LConn1":
            strategy="external_branch_insertion_preserving_fault_branch"
        elif composite:
            strategy="internal_line_terminal_insertion_required_split_bus_node"
        else:
            strategy="external_branch_insertion_single_component_port"
        line_targets.append({
          "component":component,"component_port":component_port,
          "terminal":x["terminal"],"bus_section":x["bus"],"bus_port":x["bus_port"],
          "current_variable":x["current_variable"],"composite_bus_port":composite,
          "mapping_reference_count":len(rows),"insertion_strategy":strategy,
          "sensor":"Current Sensor (Three-Phase)",
          "series_conserving_ports":["LConn1","RConn2"],"sensor_ps_output":"RConn1"
        })
    assert sum(not x["composite_bus_port"] for x in line_targets)==65
    assert sum(x["composite_bus_port"] for x in line_targets)==3

    # Transformer current map has one record per winding terminal. Confirm that
    # each associated busbar port is a single-component connection.
    tf_groups={}
    for x in cm["transformer_current_signature_checks"]:
        key=(x["component"],x["component_port"])
        tf_groups.setdefault(key,[]).append(x)
    assert len(tf_groups)==24
    tf_targets=[]
    for (component,component_port),rows in sorted(tf_groups.items()):
        x=rows[0]
        portmap=by_port.get(bus_key(x["bus"],x["bus_port"]))
        assert portmap is not None,(component,component_port,x["bus"],x["bus_port"])
        tf_targets.append({
          "component":component,"component_port":component_port,
          "bus_section":x["bus"],"bus_port":x["bus_port"],
          "current_variable":x["current_variable"],
          "connected_port_count":portmap["connected_port_count"],
          "composite_bus_port":portmap["connected_port_count"]>1,
          "best_direct_phase_error":x["best_direct"]["direct_error"],
          "sampled_linear_fit_rank":x["best_linear"]["linear_rank"],
          "insertion_strategy":"external_branch_insertion_single_component_port" if portmap["connected_port_count"]==1 else "special_composite_insertion_review",
          "sensor":"Current Sensor (Three-Phase)",
          "series_conserving_ports":["LConn1","RConn2"],"sensor_ps_output":"RConn1"
        })
    direct_tf=sum(not x["composite_bus_port"] for x in tf_targets)
    assert direct_tf==24,("unexpected composite transformer ports",direct_tf)

    composite=[x for x in line_targets if x["composite_bus_port"]]
    report={
      "status":"PASS_TOPOLOGY_GROUNDED_FULL_GRID_SENSOR_INSERTION_PLAN",
      "model":"IEEE39BusSystem_AEFCStress",
      "source_busbar_topology_run_id":45928516528,
      "source_current_variable_map_run_id":45928276856,
      "physical_bus_sections":41,
      "line_components":34,
      "transformer_components":12,
      "sensor_target_counts":{
        "bus_voltage_sensors":len(voltage),
        "line_terminal_current_sensors":len(line_targets),
        "transformer_winding_current_sensors":len(tf_targets),
        "total_sensor_blocks":len(voltage)+len(line_targets)+len(tf_targets)
      },
      "line_terminal_mapping":{"direct_single_component":65,"composite":3,"unique_terminals":68},
      "transformer_winding_mapping":{"direct_single_component":direct_tf,"composite":24-direct_tf,"unique_terminals":24},
      "bus_voltage_sensor_targets":voltage,
      "line_current_sensor_targets":line_targets,
      "transformer_current_sensor_targets":tf_targets,
      "composite_line_endpoint_special_handling":composite,
      "full_grid_sensor_instrumentation_implemented":False,
      "sensor_calibration_verified":False,
      "sensor_error_bounds_verified":False,
      "plant_nonperturbation_verified":False,
      "full_network_safety_certified":False,
      "interpretation":(
        "This is a topology-grounded insertion plan, not an instrumented model. It identifies 41 shunt bus-voltage "
        "sensor targets, 68 line terminal-current targets and 24 transformer winding-current targets. The three "
        "composite line endpoints must not be handled by a naive one-edge insertion: the Bus16 fault-sharing "
        "endpoint can use the branch-specific pattern being piloted, while the two split-bus endpoints require "
        "internal line-terminal sensing or a verified multi-edge isolation strategy. No sensor accuracy, trusted "
        "measurement, plant nonperturbation, thermal limit, or full-grid safety claim is established."
      )
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","sensor_target_counts","line_terminal_mapping","transformer_winding_mapping","composite_line_endpoint_special_handling")},indent=2))

if __name__=="__main__":
    main()
