"""Fail closed on incomplete or mixed-version cohorts; statistics use training seeds."""
import argparse, csv, hashlib, itertools, json, math
from pathlib import Path
import numpy as np

MAIN=('adv','ordinary','adv_no_cw','dense','dense_cw','maddpg_ac')
HET=('adv','no_adapter','no_prototype','dense')
FACTORS=tuple('r5_'+''.join(map(str,b)) for b in itertools.product((0,1),repeat=4))
METRICS=('terminal_load_pct','safe_dwell_pct','restricted_score','no_dwell_count')
TARGET={'adv':[96.80,72.40,20.74,276], 'ordinary':[93.60,47.80,26.03,522],
        'adv_no_cw':[95.20,58.60,23.61,414], 'dense':[94.10,53.40,24.94,466],
        'dense_cw':[94.60,46.20,25.77,538], 'maddpg_ac':[92.90,41.50,27.86,585]}

def need(q,msg):
    if not q: raise ValueError(msg)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
    return h.hexdigest()

def describe(values):
    x=np.asarray(values,dtype=float); n=len(x)
    need(n>=2 and np.isfinite(x).all(),'invalid seed values')
    rng=np.random.default_rng(20261118)
    sample=x[rng.integers(0,n,(20000,n))].mean(axis=1)
    lo,hi=np.quantile(sample,[.025,.975])
    return dict(n=n,mean=float(x.mean()),sd=float(x.std(ddof=1)),ci95_low=float(lo),ci95_high=float(hi))

def signflip(values):
    x=np.asarray(values,dtype=float)
    null=np.asarray(list(itertools.product((-1,1),repeat=len(x))))@x
    return float(np.mean(np.abs(null)>=abs(x.sum())-1e-10))

def holm(rows):
    prev=0.; n=len(rows)
    for i,row in enumerate(sorted(rows,key=lambda a:a['p_exact_signflip'])):
        prev=max(prev,min(1.,(n-i)*row['p_exact_signflip'])); row['p_holm']=prev

def csvout(path,rows):
    need(rows,'empty '+str(path)); fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def episode(ep, factor=None):
    trace=ep['trace'];need(1<=len(trace)<=30,'trace length')
    first=-1; consecutive=0
    for i,z in enumerate(trace):
        need(int(z['t'])==i+1,'step sequence')
        physical=bool(z['ac_converged']) and float(z['thermal_excess_pct_sum'])<=1e-7 and float(z['voltage_violation_pu_sum'])<=1e-7
        need(bool(z['safe'])==physical,'safety flag mismatch')
        consecutive=consecutive+1 if physical and z['restored_pct']>=90 else 0
        if consecutive>=5 and first<0:first=i-3
        if factor is not None:
            bits=list(map(int,factor[3:])); target=0 if bits[2] else 4; active=5<=i<16
            need(z['factor_bits']==bits and int(z['attack_target'])==target and bool(z['attack_active'])==active,'factor metadata mismatch')
            raw=np.array(z['raw_observation']); obs=raw.copy()
            if bits[1] and i>=2:obs[1::2,1:4]=np.array(trace[i-2]['raw_observation'])[1::2,1:4]
            if active:obs[target,1]+=.12;obs[target,2]-=.09
            if bits[0]:obs[1::2,2]=0
            need(np.allclose(obs,z['controller_observation'],atol=2e-6,rtol=1e-6),'mask/delay/attack observation mismatch')
            cmd=np.array(z['raw_command']);
            if bits[3]:cmd[1::2]=np.minimum(cmd[1::2],.6)
            if active:cmd[target]=np.clip(cmd[target]-.25,0,1)
            need(np.allclose(cmd,z['executed_command'],atol=1e-8),'command intervention mismatch')
            prev=np.full(5,.65) if i==0 else np.array(trace[i-1]['client_served_fraction'])
            need(np.allclose(np.clip(prev+.018*np.clip(cmd,0,1),0,1),z['client_served_fraction'],atol=1e-7),'physical increment mismatch')
    need(first==int(ep['recovery_step']) and int(first>=0)==int(ep['safe_dwell5']) and int(first<0)==int(ep['censored']),'recovery/censor mismatch')
    need(abs(float(ep['final_restored_pct'])-float(trace[-1]['restored_pct']))<1e-7,'terminal load mismatch')
    return float(trace[-1]['restored_pct']),int(first>=0),first if first>=0 else 31,int(first<0)

def assess(p,study):
    d=json.loads(p.read_text());s=d['summary'];m=json.loads(p.with_suffix('.manifest.json').read_text())
    ctrl=s['r5_control'];f=s['r5_factor'];seed=int(s['seed']);key=(seed,f,ctrl)
    need(s['r5_study']==study and s['case']==39 and s['clients']==5 and s['backend']=='pandapower AC quasi-static','study protocol mismatch')
    need(s['train_episodes']==1000 and s['completed_rounds']==200 and s['eval_episodes']==10 and s['steps_per_episode']==30,'budget mismatch')
    need(len(d['train_episodes'])==1000 and len(d['tests'])==10,'incomplete records')
    need(m['source_json_sha256']==sha(p) and m['checkpoint_sha256']==sha(p.with_suffix('.pt')),'hash mismatch')
    need(m['training_episodes_executed']==1000,'manifest budget')
    if ctrl!='maddpg_ac':
        need(len(d['rounds'])==200 and sum(x['uplink_bytes'] for x in d['rounds'])==s['uplink_bytes'],'round accounting')
        need(s['record_training_trace']==1 and s['malicious_clients']==0,'unexpected attack or tracing')
        need(s['batch_size']==256 and s['hidden_size']==128 and s['latent_size']==32 and s['local_fit_steps']==5 and s['sharing_steps']==2 and abs(s['kappa']-.2)<1e-12,'optimizer budget')
        if study=='hetero':
            need(s['attack']=='physical' and s['fixed_traffic']==1 and s['observation_dimensions']==[6]*5,'heterogeneity base mismatch')
            need((sum(s['per_client_encoder_parameters'])==0 and sum(s['per_client_head_parameters'])==0)==(ctrl=='no_adapter'),'adapter topology mismatch')
            need(bool(s['prototype_exchange_disabled'])==(ctrl=='no_prototype'),'prototype ablation mismatch')
            if ctrl=='no_prototype':
                need(all(not c.get('drift_by_category') for r in d['rounds'] for c in r['per_client']),'prototype drift in no-prototype arm')
                need(s['final_server_prototype_categories']==[],'prototype exchange in no-prototype arm')
        else:need(s['attack']=='clean' and s['fixed_traffic']==0 and s['observation_dimensions']==[6,3,6,3,6],'main protocol mismatch')
    else:need(study=='main' and s['centralized_joint_replay'] and not d['rounds'],'centralized baseline identity mismatch')
    fac=f if study=='hetero' else None
    need([e['episode'] for e in d['train_episodes']]==list(range(1,1001)),'episode numbering')
    a=np.array([episode(e,fac) for e in d['train_episodes']]);b=np.array([episode(e,fac) for e in d['tests']])
    row=dict(seed=seed,factor=f,control=ctrl,git_commit=m['git_commit'],run_id=m['github_run_id'],source_json_sha256=m['source_json_sha256'],checkpoint_sha256=m['checkpoint_sha256'],uplink_bytes=s['uplink_bytes'])
    row.update(zip(METRICS,[a[:,0].mean(),a[:,1].mean()*100,a[:,2].mean(),a[:,3].sum()]))
    row.update(zip(('heldout_load_pct','heldout_dwell_pct','heldout_restricted_score','heldout_no_dwell'),[b[:,0].mean(),b[:,1].mean()*100,b[:,2].mean(),b[:,3].sum()]))
    return key,row

def run(study,root,out,records_only=False):
    out.mkdir(parents=True,exist_ok=True); seeds=tuple(range(80,90)) if study=='main' else tuple(range(80,85))
    factors=('dim',) if study=='main' else FACTORS; controls=MAIN if study=='main' else HET
    expected=set(itertools.product(seeds,factors,controls)); records={}; errors=[]
    for p in root.rglob('*.json'):
        if p.name.endswith('.manifest.json'):continue
        try:
            if records_only:
                r=json.loads(p.read_text());need(r.pop('independent_raw_audit_passed') is True,'unaudited raw records')
                k=(r['seed'],r['factor'],r['control']);need(all(len(r[z])==64 for z in ('source_json_sha256','checkpoint_sha256')),'invalid hashes')
            else:k,r=assess(p,study)
            need(k in expected and k not in records,'unexpected/duplicate '+str(k));records[k]=r
        except Exception as e:errors.append(dict(path=str(p),error=str(e)))
    missing=sorted(expected-set(records));shas={r['git_commit'] for r in records.values()};runs={r['run_id'] for r in records.values()}
    report=dict(passed=not errors and not missing and len(shas)==1 and len(runs)==1,study=study,backend='pandapower AC quasi-static',expected_runs=len(expected),audited_runs=len(records),missing=missing,errors=errors,source_commits=sorted(shas),source_run_ids=sorted(runs),native_simulink_reproduced=False)
    (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    need(report['passed'],'incomplete or mixed cohort; see audit.json')
    csvout(out/'per_seed.csv',[records[k] for k in sorted(records)])
    metrics=METRICS if study=='main' else METRICS+('heldout_load_pct','heldout_dwell_pct','heldout_restricted_score','heldout_no_dwell')
    summary=[];paired=[]; effects=[]; comparison=[]
    for f,c,metric in itertools.product(factors,controls,metrics):
        arr=[records[s,f,c][metric] for s in seeds]
        summary.append(dict(factor=f,control=c,metric=metric,**describe(arr)))
        if c!='adv':
            delta=[records[s,f,'adv'][metric]-records[s,f,c][metric] for s in seeds]
            paired.append(dict(factor=f,control=c,metric=metric,**describe(delta),p_exact_signflip=signflip(delta)))
        if study=='main':
            target=TARGET[c][METRICS.index(metric)]; obs=np.mean(arr)
            comparison.append(dict(control=c,metric=metric,manuscript_point=target,observed_mean=obs,delta=obs-target,rounds_to_manuscript=abs(obs-target)<(.5 if metric=='no_dwell_count' else .005)))
    holm(paired);csvout(out/'summary.csv',summary);csvout(out/'paired_differences.csv',paired)
    if study=='main':
        csvout(out/'manuscript_reconciliation.csv',comparison)
        report['matches_every_manuscript_point']=all(x['rounds_to_manuscript'] for x in comparison)
        report['centralized_baseline']='new MADDPG-style AC reconstruction; not native original'
    else:
        # Standard factorial effects: average high-minus-low, or interaction
        # contrast, within each independent seed, averaging all other factors.
        for c,metric in itertools.product(controls,('heldout_load_pct','heldout_dwell_pct')):
            for order in range(1,5):
                for subset in itertools.combinations(range(4),order):
                    vals=[sum(records[s,f,c][metric]*math.prod(1 if f[3+j]=='1' else -1 for j in subset) for f in factors)/8 for s in seeds]
                    effects.append(dict(control=c,metric=metric,effect='x'.join('MDGA'[j] for j in subset),**describe(vals),p_exact_signflip=signflip(vals)))
        holm(effects);csvout(out/'factorial_effects.csv',effects)
        report['factorial']='2^4 x 4 methods x 5 seeds; five-seed exact two-sided signflip minimum p=0.0625'
    (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',choices=['main','hetero'],required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--one',action='store_true');p.add_argument('--records-only',action='store_true')
    a=p.parse_args()
    if a.one:
        _,record=assess(a.root,a.study);record['independent_raw_audit_passed']=True
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(record,indent=2)+'\n')
    else:run(a.study,a.root,a.out,a.records_only)
