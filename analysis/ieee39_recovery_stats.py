#!/usr/bin/env python3
"""Preregistered native IEEE39 physical recovery: paired seed-level inference.

Two conceptually DIFFERENT estimands:
1. Prevention / attack-end exposure: may prevent entry outside recovery set.
2. Recovery given BOTH policies exposed: time-to-20-hold event. Censored
   failures are not dropped and never marked as recovered.

Units are independently seeded trajectories, not the 181 time points.
Sampled speed/actual delivered Pref safety is not full 39bus safety proof.
"""
import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def bootstrap_seed_effect(per_seed,seed=20261125,rep=10000):
    xs=list(per_seed.values())
    if not xs:return dict(n_seeds=0,mean=None,bootstrap_ci95=None)
    obs=sum(xs)/len(xs)
    rng=random.Random(seed)
    boots=[]
    for _ in range(rep):
        boots.append(sum(xs[rng.randrange(len(xs))] for _ in xs)/len(xs))
    boots.sort()
    return dict(n_seeds=len(xs),mean=obs,
                bootstrap_ci95=[boots[int(.025*rep)],boots[min(rep-1,int(.975*rep))]],
                bootstrap_cluster_unit='independent_seed')


def exact_paired_sign_p(values):
    nonzero=[x for x in values if abs(x)>1e-12]
    n=len(nonzero)
    if n==0:return dict(n_nonzero=0,positive=0,negative=0,p_two_sided_exact=1.)
    wins=sum(x>0 for x in nonzero)
    losses=n-wins
    from math import comb
    p=min(1.,2*sum(comb(n,k) for k in range(min(wins,losses)+1))/2**n)
    return dict(n_nonzero=n,positive=wins,negative=losses,p_two_sided_exact=p)


def analyze(src,horizon_seconds=72/60):
    assert not src['full_network_safety_certified']
    pairs=src['paired_ae_fc_supervisor']
    assert pairs
    all_seeds=defaultdict(list)
    eligible=defaultdict(list)
    both=0
    prevented=0
    for x in pairs:
        seed=x['seed']
        all_seeds[seed].append(x['supervisor_minus_ae_fc_speed_error'])
        a=x['ae_fc_exposed'];b=x['supervisor_exposed']
        prevented+=int(b and not a)
        if not (a and b):continue
        both+=1
        ta=x['ae_fc_recovery_time'] if x['ae_fc_recovered'] else horizon_seconds
        tb=x['supervisor_recovery_time'] if x['supervisor_recovered'] else horizon_seconds
        assert ta is not None and tb is not None
        assert 0<=ta<=horizon_seconds+1e-9 and 0<=tb<=horizon_seconds+1e-9
        # Positive means AEFC faster or non-recovering baseline (restricted)
        eligible[seed].append(tb-ta)
    mean_seeds={s:sum(v)/len(v) for s,v in all_seeds.items()}
    exposure_seed={s:sum(v)/len(v) for s,v in eligible.items()}
    area=bootstrap_seed_effect(mean_seeds)
    recovery=bootstrap_seed_effect(exposure_seed)
    sign=exact_paired_sign_p(exposure_seed.values())
    event_count_a=sum(x['ae_fc_recovered'] for x in pairs if x['both_at_attack_end_exposed'])
    event_count_b=sum(x['supervisor_recovered'] for x in pairs if x['both_at_attack_end_exposed'])
    res=dict(
      horizon_start_to_last_eligible_20_sample_hold_seconds=horizon_seconds,
      paired_conditions=len(pairs),
      independent_seeds_all=len(all_seeds),
      both_exposed_conditions=both,
      independent_seeds_with_both_exposure=len(eligible),
      prevented_exposure_conditions_AEFC_only=prevented,
      both_exposed_recovered_AEFC=event_count_a,
      both_exposed_recovered_Supervisor=event_count_b,
      paired_normalized_ten_speed_error_difference=area,
      paired_restricted_time_to_recovery_improvement_seconds=recovery,
      paired_recovery_exact_sign_test=sign,
      statistical_recovery_success_criterion=(
        'minimum 10 independent eligible seeds, CI95 excluding 0, '
        'positive recovery gain, no post-hoc threshold or pressure tuning'),
      statistical_mechanism_recovery_gain_established=(
        len(eligible)>=10 and recovery['bootstrap_ci95'] is not None and
        recovery['bootstrap_ci95'][0]>0 and sign['p_two_sided_exact']<.05 and
        event_count_a>0),
      full_native_IEEE39_execution_safety_certified=False,
      actual_trained_AEFC_RL_checkpoint_verified=False,
      manuscript_ready_full_AEFC_recovery_claim=False,
      caveat=(
        'Restricted time-to-20-sample-hold comparisons count right-censored '
        'failures at predeclared last eligible onset. If one policy never exits '
        'the recovery set, that is prevention rather than post-exposure recovery. '
        'Positive mechanistic prototype statistics cannot prove full RL checkpoint '
        'or full 39-bus electrical safety.'));
    return res


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    d=json.loads(a.audit.read_text())
    result=analyze(d)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
