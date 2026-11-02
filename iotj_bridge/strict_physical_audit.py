#!/usr/bin/env python3
"""Independently re-evaluate AC physical safety from stored held-out traces.

This auditor is side-effect free and never calls the learning algorithm.
A voltage/thermal violation is not silently excused by restored load.
"""
import argparse,csv,json,math
from pathlib import Path

VOLT_MIN=.9;VOLT_MAX=1.1;THERMAL_MAX=100.
# Indicators stored by the same AC power-flow backend:
# voltage_violation_pu_sum and thermal_excess_pct_sum.
def evaluate_run(path,threshold=90.,dwell=5):
 data=json.loads(Path(path).read_text())
 result=data['summary'];tests=data['tests'];rows=[]
 if len(tests)!=result['eval_episodes']:raise ValueError('evaluation count mismatch')
 for i,episode in enumerate(tests):
  trace=episode['trace']
  if not trace:raise ValueError('missing physical trace')
  n=len(trace)
  for step in trace:
   if not (step['ac_converged'] in (0,1) and step['safe'] in (False,True,0,1)):
    raise ValueError('invalid simulator outcomes')
   if step['safe'] and (step['voltage_violation_pu_sum']>1e-7 or step['thermal_excess_pct_sum']>1e-7):
    raise ValueError('safe flag contradicts physical violation')
  initial_safe=bool(trace[0]['safe'])
  first_reentry=next((step['t'] for step in trace if step['safe']),None)
  safe_after_reentry=bool(first_reentry is not None and all(
     step['safe'] for step in trace if step['t']>=first_reentry))
  safe_dwell=next((trace[j]['t'] for j in range(n-dwell+1)
                   if all(step['safe'] and step['restored_pct']>=threshold
                          for step in trace[j:j+dwell])),None)
  cum_thermal=sum(max(0,float(x['thermal_excess_pct_sum'])) for x in trace)
  cum_voltage=sum(max(0,float(x['voltage_violation_pu_sum'])) for x in trace)
  violated=sum(not bool(x['safe']) for x in trace)
  safe_last=bool(trace[-1]['safe'])
  if int(safe_dwell is not None)!=episode['safe_dwell5']:
   raise ValueError('safe recovery tally conflicts with independent trace')
  rows.append({'case':result['case'],'seed':result['seed'],'method':result['method'],
        'heterogeneity':result['hetero'],'attack':result['attack'],
        'test_ordinal':i,'evaluated_steps':n,'initial_safe':int(initial_safe),
        'first_safe_reentry_step':first_reentry if first_reentry is not None else -1,
        'terminal_safe':int(safe_last),'remained_safe_after_first_reentry':int(safe_after_reentry),
        'safe_recovery_step':safe_dwell if safe_dwell is not None else -1,
        'safe_recovery_censored':int(safe_dwell is None),
        'unsafe_step_count':violated,'thermal_excess_step_sum':cum_thermal,
        'voltage_excess_step_sum':cum_voltage,
        'final_restored_pct':trace[-1]['restored_pct'],
        'physical_scope':'AC steady-state; no generator frequency, real actuator or safety proof'})
 return rows

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--input',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 args=p.parse_args()
 sources=[args.input] if args.input.is_file() else sorted(
     x for x in args.input.rglob('*.json')
     if not x.name.endswith('.manifest.json') and not x.name.endswith('audit.json'))
 if not sources:raise SystemExit('no experiment traces')
 outcomes=[]
 for f in sources:outcomes.extend(evaluate_run(f))
 args.out.parent.mkdir(parents=True,exist_ok=True)
 with args.out.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(outcomes[0]));w.writeheader();w.writerows(outcomes)
 print(json.dumps({'n_tests':len(outcomes),
  'initially_unsafe':sum(not x['initial_safe'] for x in outcomes),
  'safe_dwell_success':sum(not x['safe_recovery_censored'] for x in outcomes),
  'terminal_safe':sum(x['terminal_safe'] for x in outcomes),
  'censored_tests':sum(x['safe_recovery_censored'] for x in outcomes)}))
if __name__=='__main__':main()
