#!/usr/bin/env python3
"""Per-seed paired control comparison: same certified supervisor, learned vs fixed fallback."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

SCENES=('clean','knowledge','physical','joint')

def rows(root):
    data=list(csv.DictReader((root/'summary.csv').open()))
    by={(r['scenario'],int(r['seed'])):r for r in data}
    assert len(by)==len(data)
    return by

def mean_ci(values,seed=20261125):
    x=np.asarray(values,dtype=float)
    if not len(x):return dict(n=0,mean=None,paired_bootstrap_95=None)
    if len(x)==1: return dict(n=1,mean=float(x[0]),paired_bootstrap_95=None)
    rng=np.random.default_rng(seed)
    samples=rng.integers(0,len(x),(10000,len(x)))
    means=x[samples].mean(axis=1)
    return dict(n=len(x),mean=float(x.mean()),paired_bootstrap_95=[float(np.quantile(means,.025)),float(np.quantile(means,.975))])

def trace(path,scene,seed):
    fp=path/f'seed_{seed}_{scene}.jsonl'
    return [json.loads(line) for line in fp.read_text().splitlines()]

def episode_cost(rr,post_start,flow=(.48,.42)):
    ts=[row for row in rr if row['t']>=post_start and row['command_released']]
    if not ts:return None
    return dict(flow_error=sum((abs(row['state_true'][1]-flow[0])+abs(row['state_true'][2]-flow[1]))/2 for row in ts)/len(ts),
                command_l2=sum(float(np.linalg.norm(np.array(row['command']))) for row in ts)/len(ts))

def compare(full_path:Path, supervisor_path:Path, out_path:Path):
    a=json.loads((full_path/'manifest.json').read_text())
    b=json.loads((supervisor_path/'manifest.json').read_text())
    for name in ('seed_start','seeds','scenarios','steps','physical_load_stress','physical_post_attack_strength',
                 'attack_step_start','attack_step_end','recovery_flow_tolerance','recovery_speed_tolerance',
                 'consecutive_recovery_samples'):
        assert a[name]==b[name],('paired-contract-mismatch',name,a[name],b[name])
    assert b.get('policy_mode')=='supervisor_only'
    A=rows(full_path);B=rows(supervisor_path)
    assert A.keys()==B.keys()
    per_seed=[]; aggregate=[];start=a['attack_step_end']+1
    for scene in SCENES:
        chosen=[k for k in sorted(A) if k[0]==scene]
        delay_diff=[]; flow_diff=[]; cmd_diff=[]; action_diff=[]
        for sc,seed in chosen:
            x,y=A[(sc,seed)],B[(sc,seed)]
            assert int(x['steps'])==int(y['steps'])==a['steps'],(sc,seed,'unequal termination')
            t1=trace(full_path,sc,seed);t2=trace(supervisor_path,sc,seed)
            assert len(t1)==len(t2)==a['steps']
            assert all(abs(t1[k]['qin']-t2[k]['qin'])<1e-12 and
                       abs(t1[k]['load']-t2[k]['load'])<1e-12 and
                       np.max(np.abs(np.asarray(t1[k]['post_attack'])-
                                         np.asarray(t2[k]['post_attack'])))<1e-12 for k in range(len(t1)))
            d=None
            if x['corrected']=='True' and y['corrected']=='True':
                d=int(x['recovery_steps_from_attack_stop'])-int(y['recovery_steps_from_attack_stop'])
                delay_diff.append(d)
            c1=episode_cost(t1,start);c2=episode_cost(t2,start)
            df=(c1['flow_error']-c2['flow_error']) if c1 and c2 else None
            dc=(c1['command_l2']-c2['command_l2']) if c1 and c2 else None
            if df is not None:flow_diff.append(df)
            if dc is not None:cmd_diff.append(dc)
            action_diff.append(float(np.mean([np.linalg.norm(np.asarray(q['command'])-np.asarray(p['command']))
                                               for q,p in zip(t1,t2) if q['command_released'] and p['command_released']])))
            per_seed.append(dict(scenario=sc,seed=seed,full_exposed=x['initial_outside_recovery'],
                                 supervisor_exposed=y['initial_outside_recovery'],
                                 full_corrected=x['corrected'],supervisor_corrected=y['corrected'],
                                 delay_full_minus_supervisor=d,post_flow_mae_full_minus_supervisor=df,
                                 post_command_l2_full_minus_supervisor=dc,
                                 mean_action_l2_distance=action_diff[-1],
                                 full_gate_rejects=int(x['n_gate_rejections'])))
        aggregate.append(dict(scenario=scene,seeds=len(chosen),
                              exposed_full=sum(A[k]['initial_outside_recovery']=='True' for k in chosen),
                              exposed_supervisor=sum(B[k]['initial_outside_recovery']=='True' for k in chosen),
                              recovered_full=sum(A[k]['corrected']=='True' for k in chosen),
                              recovered_supervisor=sum(B[k]['corrected']=='True' for k in chosen),
                              recovery_delay_diff=mean_ci(delay_diff),
                              post_flow_mae_diff=mean_ci(flow_diff),
                              post_command_l2_diff=mean_ci(cmd_diff),
                              mean_action_l2_distance=mean_ci(action_diff)))
    out_path.mkdir(parents=True,exist_ok=True)
    with (out_path/'per_seed.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(per_seed[0]));writer.writeheader();writer.writerows(per_seed)
    report=dict(interpretation='Equal downstream one-step safety contract, matched exogenous streams and no oracle; not a cross-platform or full neural FRL comparison',
                statistical_unit='seed',comparison='full minus supervisor-only',
                exploratory_status='same heldout conditions used in prior low-tier study; no hyperparameters changed',
                results=aggregate)
    (out_path/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--full',required=True);p.add_argument('--supervisor',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();compare(Path(a.full),Path(a.supervisor),Path(a.output))
