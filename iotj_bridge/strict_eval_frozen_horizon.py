#!/usr/bin/env python3
"""Independent frozen model evaluation under longer AC restoration horizon.
NEVER pool 50-step horizon with 30-step main-manuscript protocol.
"""
from pathlib import Path
import argparse,json,torch,numpy as np
try:
 from .strict_agent import Agent
 from .strict_run import RecoveryGrid,run_episode
except ImportError:
 from strict_agent import Agent
 from strict_run import RecoveryGrid,run_episode

def eval_saved(path,steps=50,tests=10):
 ckpt=torch.load(path,map_location='cpu',weights_only=False)
 case=int(path.as_posix().split('case39')[0].split('case118')[0].endswith('NA') if False else 39)
 # Model case is stored in the checkpoint; no inference from path.
 case=int(ckpt['case']);seed=int(ckpt['seed']);mode=ckpt['method']
 env=RecoveryGrid(case,len(ckpt['actors']),100000+seed*100,hetero='dim',
                  attack='clean',horizon=steps)
 ob=env.reset()
 agents=[]
 for i,x in enumerate(ob):
  a=Agent(len(x),seed*100+i,hidden=128,latent=32,batch=256)
  a.actor.load_state_dict(ckpt['actors'][i])
  a.critic.load_state_dict(ckpt['critics'][i])
  a.target_actor.load_state_dict(ckpt['target_actors'][i])
  a.target_critic.load_state_dict(ckpt['target_critics'][i])
  agents.append(a)
 records=[]
 for e in range(tests):
  test=RecoveryGrid(case,len(agents),100000+seed*100+e,
                    hetero='dim',attack='clean',horizon=steps)
  result=run_episode(test,agents,explore=False,
                     noise_seed=1000000+seed*100+e,trace=True)
  trace=result['trace']
  safe_idx=next((x['t'] for x in trace if x['safe']),None)
  result['first_safe_step']=-1 if safe_idx is None else safe_idx
  result['ever_safe']=int(safe_idx is not None)
  result['unsafe_steps']=sum(not x['safe'] for x in trace)
  records.append(result)
 return {'case':case,'seed':seed,'method':mode,'horizon_steps':steps,
    'tests':len(records),'mean_final_restored_pct':float(np.mean([x['final_restored_pct'] for x in records])),
    'safe_dwell_success':sum(x['safe_dwell5'] for x in records),
    'safe_reentry_success':sum(x['ever_safe'] for x in records),
    'average_first_safe_step_over_successes':float(np.mean([x['first_safe_step'] for x in records if x['ever_safe']]))
      if any(x['ever_safe'] for x in records) else None,
    'mean_unsafe_steps':float(np.mean([x['unsafe_steps'] for x in records])),
    'warning':'Separate 50-step quasi-static sensitivity, NOT original 30-step policy result',
    'individual_tests':records}

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--checkpoint',type=Path,required=True)
 p.add_argument('--steps',type=int,default=50)
 p.add_argument('--tests',type=int,default=10)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();torch.set_num_threads(1)
 result=eval_saved(a.checkpoint,a.steps,a.tests)
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='individual_tests'}))
if __name__=='__main__':main()
