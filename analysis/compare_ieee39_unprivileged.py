#!/usr/bin/env python3
"""Paired native IEEE39 four-speed and ten-generator diagnostic comparisons with equal supervisor.

No evidence of full IEEE39 physical safety or genuine heterogeneous NN-FRL.
Time-to-recovery is ONLY comparable on seeds exposed and subsequently
corrected for both treatments; exposure rates are reported for all paired
seeds separately (avoid survivor conditioning).
"""
import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

def ci(v,seed=20261125,resamples=10000):
    v=[float(x) for x in v]
    if not v:return dict(n=0,mean=None,ci95=None)
    m=sum(v)/len(v)
    if len(v)==1:return dict(n=1,mean=m,ci95=None)
    rng=random.Random(seed)
    n=len(v)
    draws=sorted(sum(v[rng.randrange(n)] for _ in range(n))/n for _ in range(resamples))
    return dict(n=n,mean=m,ci95=[draws[int(.025*resamples)],draws[int(.975*resamples)-1]])

def audit(path:Path):
    rows=list(csv.DictReader((path/'summary.csv').open()))
    group=defaultdict(dict)
    for r in rows:
        key=(r['attack_scale'],r['scenario'],int(r['seed']))
        assert r['method'] not in group[key],('duplicate',key,r['method'])
        group[key][r['method']]=r
    bycell=defaultdict(list)
    for (scale,scene,seed),m in group.items():
        bycell[(scale,scene)].append((seed,m))
    results=[]
    for (scale,scene),episodes in sorted(bycell.items()):
        episodes.sort(key=lambda x:x[0])
        ids=[k for k in episodes[0][1]]
        assert 'Supervisor-only' in ids
        assert all(set(m)==set(ids) for _,m in episodes)
        for method in ids:
            if method=='Supervisor-only':continue
            all_pairs=[(m[method],m['Supervisor-only']) for _,m in episodes]
            exposure_in_treat=sum(float(a['exposed_at_attack_stop']) for a,b in all_pairs)
            exposure_in_control=sum(float(b['exposed_at_attack_stop']) for a,b in all_pairs)
            recovered_in_treat=sum(float(a['strict_recovered']) for a,b in all_pairs)
            recovered_in_control=sum(float(b['strict_recovered']) for a,b in all_pairs)
            physical_pair_exposure=sum(int(a['exposed_at_attack_stop']=='1' and b['exposed_at_attack_stop']=='1')
                                       for a,b in all_pairs)
            both_recovered=[(a,b) for a,b in all_pairs if
                            a['strict_recovered']=='1' and b['strict_recovered']=='1']
            time_diff=[float(a['time_from_attack_stop'])-float(b['time_from_attack_stop'])
                       for a,b in both_recovered
                       if a['time_from_attack_stop'] and b['time_from_attack_stop']
                       and math.isfinite(float(a['time_from_attack_stop']))
                       and math.isfinite(float(b['time_from_attack_stop']))]
            mean_speed_diff=[float(a['mean_native_speed_error'])-float(b['mean_native_speed_error'])
                             for a,b in all_pairs]
            ten_exposed_treat=sum(int(a['all_ten_speed_exposed_at_attack_stop']=='1') for a,b in all_pairs)
            ten_exposed_control=sum(int(b['all_ten_speed_exposed_at_attack_stop']=='1') for a,b in all_pairs)
            ten_recovered_treat=sum(int(a['all_ten_speed_strict_recovered']=='1') for a,b in all_pairs)
            ten_recovered_control=sum(int(b['all_ten_speed_strict_recovered']=='1') for a,b in all_pairs)
            ten_both_recovered=[(a,b) for a,b in all_pairs if
                a['all_ten_speed_strict_recovered']=='1' and b['all_ten_speed_strict_recovered']=='1']
            ten_time_diff=[float(a['all_ten_speed_recovery_time'])-float(b['all_ten_speed_recovery_time'])
                           for a,b in ten_both_recovered
                           if math.isfinite(float(a['all_ten_speed_recovery_time']))
                           and math.isfinite(float(b['all_ten_speed_recovery_time']))]
            ten_error_diff=[float(a['mean_all_ten_speed_error'])-float(b['mean_all_ten_speed_error'])
                            for a,b in all_pairs]
            violations_treat=sum(int(float(a['speed_proxy_violation_steps'])) for a,b in all_pairs)
            violations_control=sum(int(float(b['speed_proxy_violation_steps'])) for a,b in all_pairs)
            results.append(dict(attack_scale=scale,scenario=scene,method=method,
                  baseline='Supervisor-only (same four-speed surrogate checker)',n_seeds=len(all_pairs),
                  exposed_method=exposure_in_treat,exposed_baseline=exposure_in_control,
                  recovered_method=recovered_in_treat,recovered_baseline=recovered_in_control,
                  matched_both_exposed=physical_pair_exposure,matched_both_recovered=len(both_recovered),
                  recovery_time_diff_seconds=ci(time_diff),
                  mean_normalized_speed_error_diff=ci(mean_speed_diff),
                  all_ten_generator_speed_exposed_method=ten_exposed_treat,
                  all_ten_generator_speed_exposed_baseline=ten_exposed_control,
                  all_ten_generator_recovered_method=ten_recovered_treat,
                  all_ten_generator_recovered_baseline=ten_recovered_control,
                  all_ten_both_recovered=len(ten_both_recovered),
                  all_ten_speed_recovery_time_diff_seconds=ci(ten_time_diff),
                  all_ten_generator_mean_speed_error_diff=ci(ten_error_diff),
                  speed_proxy_violations_method=violations_treat,
                  speed_proxy_violations_baseline=violations_control))
    report=dict(scope='all ten generator physical speeds evaluated, only four used online; NO full IEEE39 state safety certificate',
                statistical_unit='seed (fixed deterministic phases); pilot inference exploratory',
                pairing='same seed, model, attack schedule, physical and proxy supervisor; baseline Supervisor-only',
                hazard='recovery-time statistics are conditional on both methods exposed/recovered; use full event counts',
                results=results)
    (path/'paired_diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--results',required=True,type=Path)
    audit(a.parse_args().results)
