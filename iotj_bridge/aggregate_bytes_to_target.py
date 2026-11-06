#!/usr/bin/env python3
"""Aggregate exactly 20 pre-registered matched IEEE39 joint-attack BTT runs.

Never impute endpoint budgets to right-censored event times. The 200-round
budget is a follow-up limit, not an observed time-to-recovery for non-events.
"""
from __future__ import annotations
import argparse, collections, csv, json, math, pathlib, statistics, sys

METHODS=("adv","ordinary")
SEEDS=tuple(range(80,90))
EXPECTED={(seed,method) for seed in SEEDS for method in METHODS}

def csvwrite(path,rows,keys):
    with path.open("w",newline="",encoding="utf-8") as fp:
        w=csv.DictWriter(fp,fieldnames=keys,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    records={};errors=[];per_round=[]
    for p in sorted(args.input.rglob("bytes_to_target_summary.json")):
        s=json.loads(p.read_text())
        r=p.parent.parent
        key=(int(s["seed"]),s["method"])
        if key in records:
            errors.append(f"duplicate result seed/method: {key}")
            continue
        if s["case"]!=39 or s["attack"]!="joint" or s["hetero"]!="dim":
            errors.append(f"inconsistent grid/attack/heterogeneity: {key}")
        if s["planned_rounds"]!=200 or s["completed_rounds"]!=200:
            errors.append(f"incomplete budget: {key}")
        if not s["fixed_traffic"]:
            errors.append(f"fixed application payload not enabled: {key}")
        audits=list(r.rglob("audit_summary.json"))
        if len(audits)!=1 or not json.loads(audits[0].read_text()).get("valid",False):
            errors.append(f"missing/failing independent audit: {key}")
        raw=list(r.glob("run.json"))
        if len(raw)!=1:
            errors.append(f"missing raw run JSON: {key}")
        rounds=[json.loads(x) for x in (p.parent/"round_validation.jsonl").read_text().splitlines() if x.strip()]
        if len(rounds)!=201:errors.append(f"missing round snapshots: {key}")
        else:
            for z in rounds:
                per_round.append({"seed":key[0],"method":key[1],
                   "attack":s["attack"],"case":s["case"],
                   "round_1based":z["round_1based"],
                   "cumulative_uplink_bytes":z["cumulative_serialized_uplink_bytes"],
                   "joint_successes_10":z["validation_joint_successes"],
                   "load_only_successes_10":z["validation_load_only_successes"]})
        records[key]=s
    if set(records)!=EXPECTED:
        errors.append(f"missing={sorted(EXPECTED-set(records))}, unexpected={sorted(set(records)-EXPECTED)}")
    rows=[]
    for key,s in sorted(records.items()):
        jr=s["joint_target"];lr=s["load_only_target"]
        # A censored event time is NULL; the endpoint is recorded separately.
        rows.append({"seed":key[0],"method":key[1],"case":s["case"],"attack":s["attack"],
            "rounds_observed":s["completed_rounds"],
            "endpoint_observed_bytes":s["final_cumulative_serialized_uplink_bytes"],
            "joint_event":int(jr["event_observed"]),
            "joint_first_round":jr["first_event"]["round_1based"] if jr["first_event"] else None,
            "joint_bytes_to_target":jr["bytes_to_target"],
            "joint_right_censored":int(not jr["event_observed"]),
            "load_event":int(lr["event_observed"]),
            "load_first_round":lr["first_event"]["round_1based"] if lr["first_event"] else None,
            "load_bytes_to_target":lr["bytes_to_target"],
            "load_right_censored":int(not lr["event_observed"]),
            "test_joint_at_validation_selected":s["independent_test_summary"].get(
               "first_validation_joint",{}).get("joint_successes"),
            "test_load_at_validation_selected":s["independent_test_summary"].get(
               "first_validation_load_only",{}).get("load_only_successes"),
            "test_joint_terminal":s["independent_test_summary"]["terminal"]["joint_successes"],
            "test_load_terminal":s["independent_test_summary"]["terminal"]["load_only_successes"]
        })
    keys=["seed","method","case","attack","rounds_observed","endpoint_observed_bytes",
          "joint_event","joint_first_round","joint_bytes_to_target","joint_right_censored",
          "load_event","load_first_round","load_bytes_to_target","load_right_censored",
          "test_joint_at_validation_selected","test_load_at_validation_selected",
          "test_joint_terminal","test_load_terminal"]
    csvwrite(args.out/"per_seed_results.csv",rows,keys)
    csvwrite(args.out/"per_round_validation.csv",per_round,[
        "seed","method","attack","case","round_1based","cumulative_uplink_bytes",
        "joint_successes_10","load_only_successes_10"])
    groups=[]
    for method in METHODS:
        g=[r for r in rows if r["method"]==method]
        for family in ("joint","load"):
            successful=[r[f"{family}_bytes_to_target"] for r in g if r[f"{family}_event"]]
            rounds=[r[f"{family}_first_round"] for r in g if r[f"{family}_event"]]
            groups.append({"method":method,"criterion":family,
                "n_seeds":len(g),"observed_targets":len(successful),
                "right_censored":sum(r[f"{family}_right_censored"] for r in g),
                "conditional_median_bytes_among_events":statistics.median(successful) if successful else None,
                "conditional_median_first_round_among_events":statistics.median(rounds) if rounds else None,
                "max_followup_round":200,
                "endpoint_budget_bytes":g[0]["endpoint_observed_bytes"] if g and len({v["endpoint_observed_bytes"] for v in g})==1 else None,
                "non_event_bytes_to_target_policy":"NULL; do NOT substitute endpoint budget",
                "byte_scope":"measured serialized application uplink; not network-wire bytes"})
    csvwrite(args.out/"group_summary.csv",groups,[
        "method","criterion","n_seeds","observed_targets","right_censored",
        "conditional_median_bytes_among_events",
        "conditional_median_first_round_among_events",
        "max_followup_round","endpoint_budget_bytes",
        "non_event_bytes_to_target_policy","byte_scope"])
    overall={"valid":not errors,"expected_runs":len(EXPECTED),"received_runs":len(rows),
             "protocol":"IEEE39 / joint attack / dim adapters / 5 clients / fixed serialized application payload / 200 rounds / 10 paired seeds / 10 fixed validation trajectories and disjoint test trajectories",
             "comparison":"AEFC advantage-weighted Top-k (adv) vs ordinary-loss Top-k (ordinary)",
             "disclosure":"40,230,000 bytes (if observed) is only the 200-round terminal budget, never an imputed time-to-target",
             "group_summary":groups,"errors":errors}
    (args.out/"aggregate_audit.json").write_text(json.dumps(overall,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"valid":overall["valid"],"received_runs":len(rows),"errors":errors}))
    if errors:raise SystemExit(2)
if __name__=="__main__":main()
