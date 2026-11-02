#!/usr/bin/env python3
"""Audit immutable strict AEFC-FRL per-seed JSON outputs.

Independent unit is one complete training seed, not rounds/steps/test episodes.
No significance/claim made when no matching runs.
"""
import argparse,csv,json,math,hashlib,os
from collections import defaultdict
from pathlib import Path
import numpy as np

def audit(root,output):
 files=sorted(root.rglob("*.json"))
 rows=[];ids=set();bad=[]
 for f in files:
  try:
   d=json.loads(f.read_text())
   s=d['summary'];rounds=d['rounds'];tests=d['tests']
   identity=(s['case'],s['seed'],s['method'],s['hetero'],s['attack'],
             s['weight_cap'],s['disable_proto'])
   if identity in ids:raise ValueError("Duplicate trial identity")
   ids.add(identity)
   if len(rounds)!=s['completed_rounds'] or len(tests)!=s['eval_episodes']:
    raise ValueError("Count mismatch")
   if sum(x['uplink_bytes'] for x in rounds)!=s['uplink_bytes']:
    raise ValueError("Traffic accounting mismatch")
   if sum(int(x['safe_dwell5']) for x in tests)!=s['safe_dwell_successes']:
    raise ValueError("Safe-success mismatch")
   if any(len(x['trace'])!=s['steps_per_episode'] for x in tests):
    # Failed/nonconverged AC model may be shorter; this is documented as a failure.
    if any(x['trace'][-1]['ac_converged'] for x in tests if x['trace']):
     raise ValueError("Premature termination without nonconvergence")
   if any(not math.isfinite(float(s[k])) for k in
        ('mean_test_load_pct','mean_test_load_auc_pct','max_thermal_excess','uplink_bytes')):
    raise ValueError("Nonfinite statistic")
   for t in tests:
    if t['safe_dwell5'] and not any(
         all(z['safe'] and z['restored_pct']>=90 for z in t['trace'][j:j+5])
         for j in range(max(0,len(t['trace'])-4))):
     raise ValueError("Spurious safety certification")
   rows.append(s)
  except Exception as e:bad.append((str(f),str(e)))
 output.mkdir(parents=True,exist_ok=True)
 if not rows:raise ValueError("No valid strict training output")
 header=sorted({k for row in rows for k in row})
 with (output/'all_runs.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=header);w.writeheader();w.writerows(rows)
 groups=defaultdict(list)
 for s in rows:groups[(s['case'],s['method'],s['hetero'],s['attack'],s['weight_cap'],s['disable_proto'])].append(s)
 aggregate=[]
 for key,values in sorted(groups.items(),key=str):
  recovered=np.array([x['mean_test_load_pct'] for x in values])
  success=np.array([x['safe_dwell_successes']/x['test_count'] for x in values])
  traffic=np.array([x['uplink_bytes'] for x in values])
  aggregate.append({'case':key[0],'method':key[1],'hetero':key[2],'attack':key[3],
    'weight_cap':key[4],'disable_proto':key[5],
    'unique_train_seeds':len({x['seed'] for x in values}),
    'mean_final_restored_pct':float(recovered.mean()),
    'sd_final_restored_pct':float(recovered.std(ddof=1)) if len(values)>1 else None,
    'mean_safe_dwell_success':float(success.mean()),
    'mean_application_uplink_bytes':float(traffic.mean()),
    'mean_malicious_weight':float(np.mean([x['mean_malicious_weight'] for x in values]))})
 with (output/'aggregate.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=aggregate[0]);w.writeheader();w.writerows(aggregate)
 paired=[]
 for case in (39,118):
  base={x['seed']:x for x in rows if x['case']==case and x['method']=='adv' and x['attack']=='clean'
       and x['hetero']=='dim' and x['disable_proto']==0}
  for method in ('ordinary','random','td','uniform_high'):
   comp={x['seed']:x for x in rows if x['case']==case and x['method']==method
         and x['attack']=='clean' and x['hetero']=='dim' and x['disable_proto']==0}
   seeds=sorted(set(base).intersection(comp))
   if not seeds:continue
   delta=np.array([base[i]['mean_test_load_pct']-comp[i]['mean_test_load_pct'] for i in seeds])
   if len(seeds)>=2:
    rng=np.random.default_rng(178);draws=rng.choice(delta,size=(10000,len(delta)),replace=True).mean(axis=1)
    lo,hi=np.quantile(draws,[.025,.975])
   else:lo=hi=None
   paired.append({'case':case,'contrast':'adv-minus-'+method,'matched_train_seeds':len(seeds),
                  'mean_delta_percentage_points':float(delta.mean()),
                  'bootstrap95_low':None if lo is None else float(lo),
                  'bootstrap95_high':None if hi is None else float(hi)})
 if paired:
  with (output/'paired.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=paired[0]);w.writeheader();w.writerows(paired)
 status={'files_scanned':len(files),'valid_runs':len(rows),'rejected_runs':bad,
         'study':'experimental AC steady-state strict local PER AEFC; not dynamic grid restoration',
         'completed_full_manuscript_budget':all(x['train_episodes']>=1000 and x['steps_per_episode']>=30 for x in rows),
         'safety_conditions':['v_pu within .9-1.1','line/trafo loading <=100%','90% restored for 5 steps'],
         'statistical_independent_unit':'training seed',
         'notes':'Matched seed bootstrap is exploratory unless the final frozen protocol is completed.'}
 (output/'audit.json').write_text(json.dumps(status,indent=2)+'\n')
 print(json.dumps({'valid':len(rows),'bad':len(bad),'paired_contrasts':paired}))
 if bad:raise SystemExit(2)

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--input',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();audit(a.input,a.out)
