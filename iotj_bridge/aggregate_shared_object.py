#!/usr/bin/env python3
"""Paired 10-seed factorial analysis of shared object and AEFC component effects.

Primary: same seeds, AC task and bytes; shared actor vs shared critic.
Secondary: within each shared object, remove exactly one mechanism.
Bootstrap intervals are exploratory and do not override observed signs.
"""
from __future__ import annotations
import argparse,csv,json,math,pathlib,numpy as np

SEEDS=range(80,90)
ARCH=('actor','critic')
COMP=('full','no_adv','no_proto','no_cred')
CONDITIONS=tuple([('clean','full')]+[('joint',c) for c in COMP])
EXPECTED={(s,a,attack,comp) for s in SEEDS for a in ARCH
          for attack,comp in CONDITIONS}

def getrun(path):
 d=json.loads(path.read_text())
 return d['summary']

def difference(a,b,key):
 return float(a[key])-float(b[key])

def compare(rows,name,metric='mean_final_restored_pct'):
 delta=np.asarray([r['delta'] for r in rows],dtype=float)
 rng=np.random.default_rng(20261106)
 ix=rng.integers(0,len(delta),size=(10000,len(delta)))
 means=delta[ix].mean(axis=1)
 low,high=np.quantile(means,[.025,.975])
 return {'contrast':name,'metric':metric,'n_seeds':len(delta),
         'mean_paired_delta':float(delta.mean()),
         'median_paired_delta':float(np.median(delta)),
         'bootstrap95_low_exploratory':float(low),
         'bootstrap95_high_exploratory':float(high),
         'positive_pairs':int((delta>0).sum()),
         'zero_pairs':int((delta==0).sum()),
         'negative_pairs':int((delta<0).sum()),
         'deltas_by_seed':{str(r['seed']):float(r['delta']) for r in rows}}

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--input',type=pathlib.Path,required=True)
 p.add_argument('--out',type=pathlib.Path,required=True)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 errors=[];data={};paths=list(a.input.rglob('run.json'))
 for path in paths:
  try:
   s=getrun(path)
   k=(int(s['seed']),s['architecture'],s['attack'],s['component'])
   if k in data:
    errors.append(f'duplicate {k}');continue
   data[k]=s
   if s['protocol']!='controlled-share-object-v1' or s['case']!=39 or s['hetero']!='dim':
    errors.append(f'protocol mismatch: {k}')
   if s['episodes']!=1000 or s['completed_rounds']!=200 or s['eval_episodes']!=10:
    errors.append(f'budget mismatch: {k}')
   if not s['fixed_traffic']:
    errors.append(f'nonfixed serialized traffic: {k}')
  except Exception as exc:
   errors.append(f'{path}: {type(exc).__name__}: {exc}')
 if set(data)!=EXPECTED:
  errors.append(f'missing={sorted(EXPECTED-set(data))}, unexpected={sorted(set(data)-EXPECTED)}')
 # Validate separate independent-audit results. Runs that lack the audit are NOT accepted.
 for k,s in data.items():
  # Each job uploaded one local audit summary next to the run.
  pth=next((q for q in paths if q.parent.name==s['architecture'] and False),None)
  # Verify whole archive via discovered independent audit files later below.
 audits=list(a.input.rglob('independent_audit.json'))
 accepted=set()
 for q in audits:
  try:
   j=json.loads(q.read_text())
   if not j['valid'] or j['valid_runs']!=1:
    errors.append(f'invalid run audit: {q}');continue
   per=json.loads((q.parent/'independent_runs.json').read_text())
   if len(per)!=1:errors.append(f'non-unique audit {q}');continue
   v=per[0]
   k=(int(v['seed']),v['architecture'],v['attack'],v['component'])
   if k in accepted:errors.append(f'duplicate independent audit {k}')
   accepted.add(k)
   if not v['valid']:errors.append(f'invalid audit result for {k}')
  except Exception as exc:errors.append(f'bad independent audit {q}: {exc}')
 if accepted!=EXPECTED:errors.append(f'audit missing={sorted(EXPECTED-accepted)}')
 source_sha={v['code_commit_sha'] for v in data.values()}
 if len(source_sha)!=1:errors.append('mixed code versions in paired experiments')
 # Equal measured bytes must match for each seed, condition and ALL rounds.
 # The per-run audit verifies round-level fixed bytes. Therefore matching the
 # audited fixed round payloads ensures all 200 rounds and total match.
 for seed in SEEDS:
  for attack,component in CONDITIONS:
   ka=(seed,'actor',attack,component);kc=(seed,'critic',attack,component)
   if ka not in data or kc not in data:continue
   aa=data[ka];cc=data[kc]
   if aa['total_measured_uplink_bytes']!=cc['total_measured_uplink_bytes']:
    errors.append(f'unmatched application budget: {seed},{attack},{component}')
   if aa['k_coordinates_equal_across_arms']!=cc['k_coordinates_equal_across_arms']:
    errors.append(f'unmatched transmitted Top-k coordinates: {seed},{attack},{component}')
 per_seed=[]
 for seed in SEEDS:
  for attack,component in CONDITIONS:
   ka=(seed,'actor',attack,component);kc=(seed,'critic',attack,component)
   if ka not in data or kc not in data:continue
   A=data[ka];C=data[kc]
   per_seed.append({
    'seed':seed,'attack':attack,'component':component,
    'actor_safe_dwell_10':A['safe_dwell5_successes'],
    'critic_safe_dwell_10':C['safe_dwell5_successes'],
    'delta_actor_minus_critic_safe_dwell_10':A['safe_dwell5_successes']-C['safe_dwell5_successes'],
    'actor_mean_final_load_pct':A['mean_final_restored_pct'],
    'critic_mean_final_load_pct':C['mean_final_restored_pct'],
    'delta_actor_minus_critic_load_pct':difference(A,C,'mean_final_restored_pct'),
    'actor_unsafe_tests':A['any_unsafe_tests'],
    'critic_unsafe_tests':C['any_unsafe_tests'],
    'equal_measured_uplink_bytes':A['total_measured_uplink_bytes'] if A['total_measured_uplink_bytes']==C['total_measured_uplink_bytes'] else None
   })
 if per_seed:
  with (a.out/'paired_per_seed.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(per_seed[0]));w.writeheader();w.writerows(per_seed)
 contrasts=[]
 for attack,component in CONDITIONS:
  for metric in ('mean_final_restored_pct','safe_dwell5_successes','any_unsafe_tests'):
   deltas=[{'seed':seed,'delta':difference(data[seed,'actor',attack,component],
       data[seed,'critic',attack,component],metric)}
       for seed in SEEDS if (seed,'actor',attack,component) in data and
                           (seed,'critic',attack,component) in data]
   if len(deltas)==10:
    contrasts.append(compare(deltas,f'actor-minus-critic/{attack}/{component}',metric))
 for architecture in ARCH:
  for component in ('no_adv','no_proto','no_cred'):
   for metric in ('mean_final_restored_pct','safe_dwell5_successes'):
    deltas=[{'seed':seed,'delta':difference(data[seed,architecture,'joint','full'],
      data[seed,architecture,'joint',component],metric)}
      for seed in SEEDS if (seed,architecture,'joint','full') in data and
                             (seed,architecture,'joint',component) in data]
    if len(deltas)==10:
     contrasts.append(compare(deltas,f'full-minus-{component}/joint/{architecture}',metric))
 for component in ('no_adv','no_proto','no_cred'):
  for metric in ('mean_final_restored_pct','safe_dwell5_successes'):
   deltas=[{'seed':seed,'delta':(
      difference(data[seed,'actor','joint','full'],data[seed,'critic','joint','full'],metric)
     -difference(data[seed,'actor','joint',component],data[seed,'critic','joint',component],metric))}
     for seed in SEEDS if all((seed,ar,'joint',cp) in data for ar in ARCH for cp in ('full',component))]
   if len(deltas)==10:
    contrasts.append(compare(deltas,f'architecture-by-{component}-interaction/joint',metric))
 (a.out/'paired_contrasts.json').write_text(json.dumps(contrasts,indent=2,allow_nan=False)+'\n')
 overview={'valid':not errors,'expected_runs':len(EXPECTED),
           'obtained_runs':len(data),'independently_audited_runs':len(accepted),
           'independent_unit':'paired training seed, 10 per condition',
           'shared_objects':'actor backbone vs compatible critic hidden/output layers; private critic input and personalized local actor retained',
           'methods_are_not_a2fc':True,
           'component_interpretation':{
            'no_adv':'ordinary matched-count episode selection in local actor update',
            'no_proto':'disable local prototype alignment but retain prototype messaging/server handling',
            'no_cred':'equal aggregation weights instead of credibility weights, preserving upload metadata and clipping'},
           'byte_scope':'actual length of serialized application-layer messages; not TCP/IP wire bytes',
           'equal_byte_rule':'same number of Top-k coordinates and padded prototype fields, verified every round',
           'budget':'1000 train episodes / 200 rounds / 10 held-out fixed AC tests',
           'uncertainty':'Paired 10-seed bootstrap intervals are exploratory, no multiplicity correction',
           'caveat':'Shared actor and critic parameter blocks have different loss-gradient dynamics. The experiment identifies a controlled shared-block intervention, not a universal isolated mechanism law.',
           'source_commits':sorted(source_sha),'errors':errors}
 (a.out/'aggregate_audit.json').write_text(json.dumps(overview,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:overview[k] for k in ('valid','expected_runs','obtained_runs','independently_audited_runs','errors')}))
 if not overview['valid']:raise SystemExit(2)

if __name__=='__main__':main()
