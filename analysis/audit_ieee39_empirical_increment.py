#!/usr/bin/env python3
"""Diagnostic ONLY: held-out sampled next-step ten-generator increments.

Use real R2024b native Simulink original frozen 24 pilot episodes.
For each (method,physical/joint scenario), fit a per-component observed
max |y[t+1]-y[t]| using physical seed 0, then count bound violations in
unseen seed 1. Inflations 1,1.25,2 are a sensitivity table, NOT a validated
disturbance/model error guarantee, not continuous-time derivative bounds,
and never a complete native IEEE39 DAE reachability certificate.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

SCALES=(1.0,1.25,2.0)
N=10
EPS=1e-12
METHODS=("AEFC-Full","Supervisor-only","RobustAgg",
         "AEFC-no-PATBU","AEFC-no-Gate","AEFC-no-TGOPA")
SCENES=("physical","joint")


def process(directory,output):
    assert (directory/"manifest.json").exists()
    manifest=json.loads((directory/"manifest.json").read_text())
    assert manifest["source_commit"]=="30eb3a58bf9d092e1303e7be3492b36f6458382e"
    result=dict(source_commit=manifest["source_commit"],
       physical_observation_channels=10,
       original_online_input_channels=4,
       train_seed=0,holdout_seed=1,
       arithmetic="sampled increments only, not continuous derivatives",
       inflation_factors_exploratory=list(SCALES),
       fit_calibrated_after_inspecting_original_frozen_data=True,
       formal_IEEE39_one_step_certificate=False,
       formal_IEEE39_continuous_tube_certificate=False,
       comparison_cells=[],
       overall=[])
    overall={f:dict(covered=0,checked=0,max_ratio=0.0) for f in SCALES}
    for scene in SCENES:
        for method in METHODS:
            p=directory/"scale_1"/scene/method
            traces=[]
            for seed in (0,1):
                file=p/f"seed_{seed:02d}.jsonl"
                assert file.is_file(),file
                traces.append([json.loads(l) for l in file.read_text().splitlines()])
            assert all(len(t)==181 for t in traces)
            increments=[]
            for t in traces:
                vals=[list(map(float,x["all_ten_generator_speed_normalized"])) for x in t]
                assert all(len(v)==10 and all(math.isfinite(x) for x in v) for v in vals)
                increments.append([[vals[i+1][k]-vals[i][k] for k in range(N)]
                                   for i in range(len(vals)-1)])
            rawtrain,rawtest=increments
            maximum=[max(abs(row[k]) for row in rawtrain) for k in range(N)]
            pair=dict(method=method,scenario=scene,training_component_increments=1800,
                      independent_holdout_component_increments=1800,
                      train_max_sampled_component_increments=maximum,
                      inflation={})
            for factor in SCALES:
                bound=[factor*a+EPS for a in maximum]
                count=sum(abs(v)<=bound[k] for row in rawtest
                          for k,v in enumerate(row))
                maxr=max(abs(v)/bound[k] for row in rawtest
                         for k,v in enumerate(row))
                pair["inflation"][str(factor)]=dict(covered=count,checked=1800,
                                                    violations=1800-count,
                                                    largest_holdout_over_bound_ratio=maxr)
                overall[factor]["covered"]+=count
                overall[factor]["checked"]+=1800
                overall[factor]["max_ratio"]=max(overall[factor]["max_ratio"],maxr)
            result["comparison_cells"].append(pair)
    for factor in SCALES:
        x=overall[factor]
        x["inflation_factor"]=factor
        x["empirical_coverage_fraction"]=x["covered"]/x["checked"]
        x["violations"]=x["checked"]-x["covered"]
        assert x["checked"]==21600
        result["overall"].append(x)
    # Positive empirical coverage alone NEVER promotes a formal result.
    assert not result["formal_IEEE39_one_step_certificate"]
    assert not result["formal_IEEE39_continuous_tube_certificate"]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(result["overall"],indent=2))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    process(args.results,args.output)
