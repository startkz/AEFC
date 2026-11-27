#!/usr/bin/env python3
"""Recover generator measurement-bus field sources and selected elements from native block wiring."""
from __future__ import annotations
import json,pathlib,re
ROOT=pathlib.Path(".")
SRCROOT=ROOT/"artifacts/generator_measurement_audit"
OUT=ROOT/"results/ieee39_safety_mapping/generator_measurement_bus_schema_v2.json"

def load_unique(root,name):
    hits=list(root.rglob(name))
    assert len(hits)==1,(root,name,len(hits))
    return json.loads(hits[0].read_text(encoding="utf-8"))

def as_list(x):
    if x is None:return []
    if isinstance(x,list):return x
    if isinstance(x,dict):return [x]
    return []

def params(x):
    return {z.get("name"):z.get("value") for z in as_list(x.get("dialog_parameters",[]))}

def leaf(path):
    return path.split("/")[-1]

def source_for_converter(converter,by_path):
    for pc in as_list(converter.get("port_connectivity",[])):
        if pc.get("type")=="LConn1":
            dst=as_list(pc.get("dst_blocks",[]))
            if dst:return dst[0]
    return None

def main():
    d=load_unique(SRCROOT,"native_ieee39_generator_measurement_bus_audit_v1.json")
    blocks=as_list(d["generator_measurement_related_blocks"])
    by_path={x.get("path"):x for x in blocks}
    bus_creators=[x for x in blocks if "buscreator" in x.get("name","").replace("\n","").replace(" ","").lower()]
    gen_creators=[x for x in bus_creators if re.search(r"/Gen[0-9]+@Bus[0-9]+/Bus",x.get("path",""))]
    top_creators=[x for x in bus_creators if x not in gen_creators]
    assert len(gen_creators)==10,(len(gen_creators),[x.get("path") for x in gen_creators])
    assert len(top_creators)==1,(len(top_creators),[x.get("path") for x in top_creators])
    rows=[]
    for bc in sorted(gen_creators,key=lambda x:int(re.search(r"/Gen([0-9]+)@",x["path"]).group(1))):
        gen=re.search(r"/(Gen[0-9]+@Bus[0-9]+)",bc["path"]).group(1)
        inputs=[]
        for pc in as_list(bc.get("port_connectivity",[])):
            srcs=as_list(pc.get("src_blocks",[]))
            if not srcs:continue
            converter_path=srcs[0]
            conv=by_path.get(converter_path)
            assert conv is not None,(bc["path"],converter_path)
            meas_path=source_for_converter(conv,by_path)
            assert meas_path is not None,(converter_path,conv.get("port_connectivity"))
            meas=by_path.get(meas_path,{})
            inputs.append({
              "input_index":int(pc["index"]),
              "converter":leaf(converter_path).replace("\n"," "),
              "measurement_block":leaf(meas_path).replace("\n"," "),
              "measurement_block_path":meas_path,
              "converter_unit":params(conv).get("Unit"),
              "signal_source_verified_by_port_connectivity":True
            })
        inputs=sorted(inputs,key=lambda x:x["input_index"])
        assert [x["input_index"] for x in inputs]==[1,2,3]
        expected=["Rotor velocity","Terminal voltage","Rotor electrical angle"]
        assert [x["measurement_block"] for x in inputs]==expected,(gen,inputs)
        rows.append({"generator":gen,"bus_creator_input_count":3,"input_order":inputs})
    meas_blocks=as_list(d["measurements_subsystem_blocks"])
    elements=[]
    for x in meas_blocks:
        p=params(x)
        el=p.get("Element")
        if el:
            elements.append({"element":el,"block":x.get("name")})
    w=sorted(x["element"] for x in elements if x["element"].endswith(".w"))
    vt=sorted(x["element"] for x in elements if x["element"].endswith(".Vt"))
    assert len(elements)==20 and len(w)==10 and len(vt)==10
    muxes=[]
    for x in meas_blocks:
        if x.get("block_type")=="Mux":
            muxes.append({"name":x.get("name"),"inputs":params(x).get("Inputs"),
              "source_blocks":[src for pc in as_list(x.get("port_connectivity",[])) for src in as_list(pc.get("src_blocks",[]))]})
    assert len(muxes)==2
    report={
      "status":"PASS_GENERATOR_BUS_SCHEMA_AND_SIGNAL_SOURCE_ORDER",
      "source_run_id":45955041086,
      "runtime_vector_probe_run_id":45933102123,
      "generator_count":10,
      "generator_bus_creator_count":10,
      "top_level_mGens_bus_creator_count":1,
      "generator_measurement_bus_input_order":rows,
      "measurement_sink_selected_fields":{"rotor_velocity_w":w,"terminal_voltage_Vt":vt},
      "selected_measurement_element_count":len(elements),
      "muxes":muxes,
      "per_generator_bus_signal_source_order":["rotor velocity","terminal voltage","rotor electrical angle"],
      "runtime_mGens_vector_dimension":30,
      "runtime_probe_samples":7,
      "runtime_flattened_channel_order_verified":False,
      "rotor_angle_bus_element_identifier":"unresolved; source block and input position are verified, bus field label is not",
      "generator_measurement_bus_routed_to_aefc_controller":False,
      "current_controller_physical_measurement_channels":4,
      "trusted_sensor_integrity_verified":False,
      "sensor_error_bounds_verified":False,
      "full_network_safety_certified":False,
      "interpretation":(
        "The ten per-generator Bus Creators are wired in the order rotor velocity, terminal voltage, and rotor "
        "electrical angle. The Measurements sink selects only the ten mGenX.w and ten mGenX.Vt fields; the "
        "third angle signal is not selected by its two Mux blocks. A separate 30-dimensional runtime probe exists, "
        "but its flattened channel order and the rotor-angle bus field identifier remain unverified. The bus is "
        "not connected to AEFCNativeController and is not an authenticated sensor source."
      )
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","generator_count","generator_bus_creator_count","top_level_mGens_bus_creator_count","selected_measurement_element_count","runtime_mGens_vector_dimension","runtime_flattened_channel_order_verified","rotor_angle_bus_element_identifier")},indent=2))
    for x in rows[:2]:print(json.dumps(x,indent=2))

if __name__=="__main__":
    main()
