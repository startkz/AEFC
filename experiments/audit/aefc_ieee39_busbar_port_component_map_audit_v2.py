import json, pathlib
p=pathlib.Path("results/ieee39_safety_mapping/native_busbar_port_component_map_v2.json")
d=json.loads(p.read_text(encoding="utf-8"))
assert d["busbar_blocks"]==41
assert d["busbar_physical_ports"]==123
assert d["busbar_ports_matched"]==123
assert d["busbar_ports_unresolved"]==0
assert d["unique_connected_line_blocks"]==34
assert d["unique_connected_transformer_blocks"]==12
assert d["current_variable_order_rule"]=="I_(2k-1)=LConn_k; I_(2k)=RConn_k"
for x in d["busbar_port_mappings"]:
    k=x["bus_port_index"]
    expected=2*k-1 if x["bus_port_kind"]=="LConn" else 2*k
    assert x["current_variable_candidate"]==f"I{expected}",x
out={"status":"PASS_123_PHYSICAL_PORTS_INTERLEAVED_CANDIDATES","busbar_blocks":41,
     "busbar_physical_ports":123,"matched":123,"unresolved":0,
     "line_components":34,"transformer_components":12,
     "current_variable_order_rule":"I_(2k-1)=LConn_k; I_(2k)=RConn_k",
     "full_network_safety_certified":False}
pathlib.Path("results/ieee39_safety_mapping/busbar_port_component_map_audit_v2.json").write_text(
    json.dumps(out,indent=2)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2))
