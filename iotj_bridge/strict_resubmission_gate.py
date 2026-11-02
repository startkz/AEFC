#!/usr/bin/env python3
"""Fail-closed IoT-J resubmission evidence gate.

Claims are only enabled by completed immutable per-seed experiments.
An 'incomplete' result is a report, never a success or fabricated metric.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np
REQUIRED_CASES=(39,118)
MAIN_METHODS=('adv','ordinary')
EXPECTED_BACKEND='pandapower AC quasi-static'

def read_trial(p):
    d=json.loads(p.read_text());s=d.get('summary')
    if s is None:return None
    try:
        if len(d['rounds'])!=s['completed_rounds']:raise ValueError('round_count')
        if len(d['tests'])!=s['eval_episodes']:raise ValueError('test_count')
        if sum(r['uplink_bytes'] for r in d['rounds'])!=s['uplink_bytes']:raise ValueError('traffic_accounting')
        if len(d.get('train_episodes',[]))!=s['train_episodes']:raise ValueError('training_trace_count')
        if int(s['malicious_clients'])>int(s['clients']):raise ValueError('invalid_M/N')
        for test in d['tests']:
            steps=test['trace'];n=len(steps)
            if n==0:raise ValueError('empty_physical_trace')
            passed=any(all(x['safe'] and x['restored_pct']>=90 for x in steps[i:i+5])
                       for i in range(max(0,n-4)))
            if int(passed)!=int(test['safe_dwell5']):raise ValueError('incorrect_safe_dwell')
            for x in steps:
                if x['safe'] and (x['thermal_excess_pct_sum']>1e-7 or x['voltage_violation_pu_sum']>1e-7):
                    raise ValueError('inconsistent_AC_safe_indicator')
        m=p.with_suffix('.manifest.json');t=p.with_suffix('.pt')
        if not m.is_file() or not t.is_file():raise ValueError('no_model_evidence')
        manifest=json.loads(m.read_text())
        if manifest['checkpoint_sha256']!=hashlib.sha256(t.read_bytes()).hexdigest():raise ValueError('bad_checkpoint_hash')
        if manifest.get('source_json_sha256') and manifest['source_json_sha256']!=hashlib.sha256(p.read_bytes()).hexdigest():
            raise ValueError('bad_json_hash')
        if manifest['training_episodes_executed']!=s['train_episodes']:raise ValueError('manifest_budget_mismatch')
        return s
    except (KeyError,TypeError,ValueError) as e:raise ValueError(f'{p}: {e}')

def report(root,out,min_seeds=10,min_episodes=1000,expected_rounds=200,min_tests=10):
    sources=sorted(x for x in root.rglob('*.json') if not x.name.endswith('.manifest.json')
                   and x.name not in ('audit.json','evidence_gate.json','frozen_config.json'))
    valid=[];invalid=[]
    for p in sources:
        try:
            r=read_trial(p)
            if r is not None:valid.append((p,r))
        except Exception as e:invalid.append(str(e))
    seen={};duplicated=[]
    for p,s in valid:
        ident=(int(s['case']),str(s['method']),str(s['hetero']),str(s['attack']),
               int(s['seed']),int(s['clients']),int(s['malicious_clients']),
               str(s.get('weight_cap')),int(s.get('disable_proto',0)),
               int(s.get('disable_adapters',0)))
        if ident in seen:duplicated.append({'identity':list(ident),'paths':[str(seen[ident][0]),str(p)]})
        else:seen[ident]=(p,s)
    complete={}
    def full(x):
        return (x['backend']==EXPECTED_BACKEND and x['train_episodes']>=min_episodes
                and x['scheduled_rounds']>=expected_rounds
                and x['completed_rounds']>=expected_rounds
                and x['eval_episodes']>=min_tests
                and x['train_episode_records']==x['train_episodes'])
    for case in REQUIRED_CASES:
        for method in MAIN_METHODS:
            group={int(s['seed']):s for p,s in valid if int(s['case'])==case
                   and s['method']==method and s['attack']=='clean' and s['hetero']=='dim'
                   and full(s)}
            complete[f'{case}:{method}']={'valid_training_seeds':len(group),
                  'required_training_seeds':min_seeds,'passed_count':len(group)>=min_seeds,
                  'actual_seeds':sorted(group)}
    pairs=[]
    for case in REQUIRED_CASES:
        control={int(s['seed']):s for p,s in valid if s['case']==case and s['method']=='ordinary'
            and s['attack']=='clean' and s['hetero']=='dim' and full(s)}
        active={int(s['seed']):s for p,s in valid if s['case']==case and s['method']=='adv'
            and s['attack']=='clean' and s['hetero']=='dim' and full(s)}
        seeds=sorted(set(active)&set(control))
        if not seeds:continue
        differences=np.array([active[k]['mean_test_load_pct']-control[k]['mean_test_load_pct'] for k in seeds])
        rng=np.random.default_rng(20261102)
        resampled=rng.choice(differences,(20000,len(differences)),replace=True).mean(axis=1)
        interval=np.quantile(resampled,[.025,.975])
        pairs.append({'case':case,'n_pairs':len(seeds),'effect_mean_pp':float(differences.mean()),
                      'bootstrap_95_lower_pp':float(interval[0]),'bootstrap_95_upper_pp':float(interval[1]),
                      'all_conditions_matched':all(
                          active[k]['uplink_bytes']==control[k]['uplink_bytes'] for k in seeds)})
    non_main=['independent_real_A2FC_reimplementation',
              'prior_work_40_matched_reimplementation',
              'dynamic_39_bus_generator_frequency_and_actuation',
              'dynamic_118_bus_generator_frequency_and_actuation',
              'real_serialized_wire_level_network_traffic',
              'membership_inference_raw_predictions_independent_seeds',
              'traffic_without_oracle_attack_indicator',
              'formal_safety_invariance_guarantee']
    claims={key:{'validated':False,'reason':'Requires independent specialized evidence, not supplied by AC pilot.'}
            for key in non_main}
    gate_ok=(not invalid and not duplicated and all(v['passed_count'] for v in complete.values())
             and all(x['all_conditions_matched'] for x in pairs)
             and all(v['validated'] for v in claims.values()))
    final={'status':'COMPLETE' if gate_ok else 'INCOMPLETE',
           'experimental_code_identity':'strict PER actor-backbone AC steady-state',
           'cases':complete,'paired':pairs,
           'specialized_reviewer_requirements':claims,
           'input_json_count':len(sources),'validated_records':len(valid),
           'bad_files':invalid,'duplicate_trials':duplicated,
           'notes':['Any complete main method is only an AC recovery result, not dynamic frequency or HIL.',
                    'A comparison with unequal serialized uplink bytes is not an equal-byte comparison.',
                    'A confidence interval is not proof of advantage, privacy, robustness, or safety.',
                    'No unexecuted rows may enter the paper or response as experimental findings.']}
    out.mkdir(parents=True,exist_ok=True)
    (out/'gate_report.json').write_text(json.dumps(final,indent=2,ensure_ascii=False)+'\n')
    if pairs:
        with (out/'paired.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=pairs[0].keys());w.writeheader();w.writerows(pairs)
    report_lines=['# Independent IoT-J resubmission experimental acceptance','',
       '**Status:** '+final['status'],'',
       f'Validated per-run JSON files: {len(valid)}; failed files: {len(invalid)}; duplicate trial identities: {len(duplicated)}.','',
       'The following matrix checks each required pair of AC benchmark and core method:','']
    for k,v in complete.items():
        report_lines.append(f'- {k}: {v["valid_training_seeds"]}/{min_seeds} train seeds, '+('OK' if v['passed_count'] else 'NOT COMPLETE'))
    report_lines+=['','## Unresolved specialized evidence']
    report_lines.extend('- '+s for s in non_main)
    (out/'gate_report.md').write_text('\n'.join(report_lines)+'\n')
    print(json.dumps({'status':final['status'],'core':complete,'bad':len(invalid),'duplicate':len(duplicated)}))
    return gate_ok

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--min-seeds',type=int,default=10)
    p.add_argument('--min-episodes',type=int,default=1000)
    p.add_argument('--min-test-episodes',type=int,default=10)
    p.add_argument('--allow-incomplete',action='store_true')
    a=p.parse_args()
    ok=report(a.input,a.out,a.min_seeds,a.min_episodes,min_tests=a.min_test_episodes)
    if not ok and not a.allow_incomplete:raise SystemExit(2)
if __name__=='__main__':main()
