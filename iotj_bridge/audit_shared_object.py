#!/usr/bin/env python3
"""Independent audit of shared-object experiment. No training or model selection."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,pathlib,sys

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def audit(root,expected_episodes,expected_tests):
 root=pathlib.Path(root)
 src=root/'run.json'; meta=root/'run.manifest.json'; ckpt=root/'run.pt'
 errors=[]
 def check(ok,msg):
  if not ok:errors.append(msg)
 for p in (src,meta,ckpt):
  if not p.is_file():return {'valid':False,'errors':[f'missing {p}']}
 d=json.loads(src.read_text());m=json.loads(meta.read_text());s=d['summary']
 check(sha(src)==m['run_json_sha256'],'JSON SHA256 mismatch')
 check(sha(ckpt)==m['checkpoint_sha256'],'Checkpoint SHA256 mismatch')
 check(s['protocol']=='controlled-share-object-v1','Protocol mismatch')
 check(s['episodes']==expected_episodes,'Training episode budget mismatch')
 check(s['completed_rounds']==expected_episodes//5,'Federation round budget mismatch')
 check(len(d['train_episodes'])==expected_episodes,'Training record count mismatch')
 check([z['episode_1based'] for z in d['train_episodes']]==list(range(1,expected_episodes+1)),
       'Training episodes nonconsecutive')
 check(s['eval_episodes']==expected_tests and len(d['tests'])==expected_tests,
       'Test episodes incomplete')
 check(s['clients']==5 and s['case']==39 and s['hetero']=='dim','AC setup differs')
 check(s['fixed_traffic'] is True,'Fixed traffic disabled')
 check(s['actor_shared_params']>s['k_coordinates_equal_across_arms']>0,'Invalid k for actor')
 check(s['critic_compatible_shared_params']>=s['k_coordinates_equal_across_arms'],'Invalid k for critic')
 rounds=d['rounds'];cumulative=0
 check(len(rounds)==s['completed_rounds'],'Round record count mismatch')
 first_payload=None
 for i,r in enumerate(rounds):
  byte=int(r['uplink_bytes'])
  check(r['round_1based']==i+1,f'Round index {i} mismatch')
  check(r['training_episodes']==5*(i+1),f'Round {i} training count mismatch')
  check(byte==r['expected_serialized_bytes_before_attack'],
        f'Round {i} serialized bytes changed after message construction')
  check(byte>0,f'Round {i} zero fixed-traffic payload')
  if first_payload is None:first_payload=byte
  check(byte==first_payload,f'Round {i} fixed-size payload mismatch')
  cumulative+=byte
  check(r['cumulative_uplink_bytes']==cumulative,f'Round {i} cumulative count mismatch')
  check(r['topk_coordinates_per_client']==s['k_coordinates_equal_across_arms'],
        f'Round {i} Top-k coordinate budget mismatch')
  check(r['accepted']>=0 and r['accepted']<=5,f'Round {i} invalid accepted count')
  if s['attack']=='clean':
   check(not r['attack_active'],f'Round {i} unexpected attack in clean condition')
  else:
   check(bool(r['attack_active']),f'Round {i} joint update attack not activated')
 check(s['total_measured_uplink_bytes']==cumulative,'Summary cumulative bytes mismatch')
 check(m['total_uplink_bytes']==cumulative,'Manifest cumulative bytes mismatch')
 success=0;unsafe=0;load=[]
 for i,e in enumerate(d['tests']):
  check(e['test_seed']==100000+s['seed']*100+i,f'Test scenario seed mismatch {i}')
  trace=e['trace'];check(1<=len(trace)<=30,f'Test trace length invalid {i}')
  dwell=0;hit=False
  for z in trace:
   check(all(math.isfinite(float(z[f])) for f in
        ('restored_pct','thermal_excess_pct_sum','voltage_violation_pu_sum')),
        f'Test {i} non-finite AC measurements')
   if z['safe']:
    check(bool(z['ac_converged']) and float(z['thermal_excess_pct_sum'])<=1e-7 and
          float(z['voltage_violation_pu_sum'])<=1e-7,f'Test {i} safe contradicts AC')
   dwell=dwell+1 if (bool(z['safe']) and float(z['restored_pct'])>=90) else 0
   hit |= dwell>=5
  check(bool(e['safe_dwell5'])==hit,f'Test {i} five-step dwell mismatch')
  success+=int(hit);unsafe+=int(e['any_unsafe'])
  load.append(float(e['final_restored_pct']))
 check(success==s['safe_dwell5_successes'],'Safe-success count mismatch')
 check(unsafe==s['any_unsafe_tests'],'Unsafe test count mismatch')
 check(abs(sum(load)/len(load)-s['mean_final_restored_pct'])<1e-6,'Mean load mismatch')
 return {'valid':not errors,'errors':errors,
         'seed':s['seed'],'architecture':s['architecture'],
         'component':s['component'],'attack':s['attack'],'case':s['case'],
         'episodes':s['episodes'],'rounds':s['completed_rounds'],
         'eval_tests':len(d['tests']),'safe_successes':success,
         'mean_final_restored_pct':s['mean_final_restored_pct'],
         'mean_load_auc_pct':s['mean_load_auc_pct'],
         'any_unsafe_tests':unsafe,
         'cumulative_application_uplink_bytes':cumulative,
         'round_payload_bytes':first_payload,
         'k_coordinates':s['k_coordinates_equal_across_arms'],
         'actor_params':s['actor_shared_params'],
         'critic_compatible_params':s['critic_compatible_shared_params'],
         'mean_malicious_weight':s['mean_malicious_weight'],
         'json_sha256':m['run_json_sha256'],
         'checkpoint_sha256':m['checkpoint_sha256'],
         'source_commit':m['github_sha'],
         'run_id':m['github_run_id']}

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--input',type=pathlib.Path,required=True)
 p.add_argument('--out',type=pathlib.Path,required=True)
 p.add_argument('--episodes',type=int,default=1000)
 p.add_argument('--tests',type=int,default=10)
 a=p.parse_args()
 src=[p for p in a.input.rglob('run.json')]
 if not src:raise SystemExit('no run.json')
 rows=[]
 for f in sorted(src):
  try:rows.append(audit(f.parent,a.episodes,a.tests))
  except Exception as e:rows.append({'valid':False,'path':str(f.parent),'errors':[f'{type(e).__name__}: {e}']})
 a.out.mkdir(parents=True,exist_ok=True)
 (a.out/'independent_runs.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
 result={'valid':all(r.get('valid') for r in rows),'count':len(rows),
         'valid_runs':sum(bool(r.get('valid')) for r in rows),
         'errors':[r for r in rows if not r.get('valid')]}
 (a.out/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
 if rows:
  cols=['seed','architecture','component','attack','episodes','rounds',
        'eval_tests','safe_successes','mean_final_restored_pct',
        'mean_load_auc_pct','any_unsafe_tests','cumulative_application_uplink_bytes',
        'round_payload_bytes','k_coordinates','actor_params',
        'critic_compatible_params','mean_malicious_weight','source_commit','valid']
  with (a.out/'per_run_summary.csv').open('w',newline='') as fp:
   writer=csv.DictWriter(fp,fieldnames=cols,extrasaction='ignore')
   writer.writeheader();writer.writerows(rows)
 print(json.dumps(result,allow_nan=False))
 if not result['valid']:raise SystemExit(2)

if __name__=='__main__':main()
