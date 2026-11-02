#!/usr/bin/env python3
"""Model-predictive safe-action shield for frozen AEFC-FRL on AC grids.

For each proposed actuation, solve actual AC power flow BEFORE execution.
When a feasible candidate exists, execute only a feasible one. If the
current point is infeasible and no candidate can make the next point safe,
minimize predicted constraint violations; report infeasibility explicitly.
This is a hard decision gate in the simulated model, not grid-frequency
invariance, dynamic Simulink validation, or hardware execution.
"""
import argparse, json, math
from pathlib import Path
import numpy as np
import torch
try:
 from .strict_agent import Agent
 from .strict_run import RecoveryGrid
except ImportError:
 from strict_agent import Agent
 from strict_run import RecoveryGrid

class PredictiveACShield(RecoveryGrid):
    def __init__(self,*args,shield=True,**kwargs):
        self.shield_enabled=bool(shield)
        self.shield_audit=[]
        super().__init__(*args,**kwargs)
    def reset(self):
        self.shield_audit=[]
        return super().reset()
    def forecast(self,command):
        # Never change the actual step count, controller, or physical state.
        old_served=self.served.copy()
        old_scaling=self.net.load.scaling.to_numpy(copy=True)
        future=np.clip(old_served+0.018*np.clip(np.asarray(command),0.,1.),0,1)
        for i,indices in enumerate(self.groups):
            self.net.load.iloc[indices,self.net.load.columns.get_loc('scaling')]=future[i]
        self._solve()
        pred={'converged':bool(self.valid),'voltage':float(self.voltage_excess),
              'thermal':float(self.thermal_excess),
              'served_pct':100*float(np.sum([self.demand[ids].sum()*future[i]
                  for i,ids in enumerate(self.groups)])/self.demand.sum())}
        pred['feasible']=pred['converged'] and pred['voltage']<=1e-7 and pred['thermal']<=1e-7
        self.served=old_served
        self.net.load.loc[:,'scaling']=old_scaling
        self._solve()
        return pred
    def step(self,action):
        requested=np.clip(np.asarray(action,dtype=float),0,1)
        before=self.forecast(requested)
        selected=requested.copy();selected_result=before;found=bool(before['feasible'])
        evaluated=1
        if self.shield_enabled:
            # Include the unmodified requested action in the candidate set.
            candidates=[requested,np.ones_like(requested),0.75*requested,
                        0.5*requested,np.zeros_like(requested)]
            candidates.extend(np.eye(len(requested)))
            candidates.extend(np.ones_like(requested)-np.eye(len(requested)))
            scored=[]
            for cmd in candidates:
                p=before if np.array_equal(cmd,requested) else self.forecast(cmd)
                evaluated+=not np.array_equal(cmd,requested)
                score=(p['thermal']+100*p['voltage']+(1e5 if not p['converged'] else 0))
                scored.append((cmd,p,score))
            feasible=[x for x in scored if x[1]['feasible']]
            if feasible:
                # Minimal intervention: project to nearest feasible candidate; use served demand only to break ties.
                selected,selected_result,_=min(feasible,key=lambda z:(float(np.linalg.norm(z[0]-requested)), -z[1]['served_pct']))
                found=True
            else:
                # No false claim of hard safety: fail-closed to the best
                # predicted violation reduction from the candidate set.
                selected,selected_result,_=min(scored,key=lambda z:(z[2],-z[1]['served_pct']))
                found=False
        obs,reward,done,info=super().step(selected)
        report={'requested_feasible':int(before['feasible']),
                'feasible_candidate_found':int(found),
                'selected_feasible':int(selected_result['feasible']),
                'enforced_action_change':int(not np.allclose(requested,selected,atol=1e-9)),
                'candidate_evaluations':int(evaluated),
                'forecast_thermal_excess':selected_result['thermal'],
                'forecast_voltage_excess':selected_result['voltage'],
                'actual_safe':int(info['safe']),
                'shield_contract_mismatch':int(bool(selected_result['feasible']) and not info['safe'])}
        self.shield_audit.append(report)
        return obs,reward,done,info

def frozen_evaluation(checkpoint_path,shield=True,case=None,seed=80,tests=10,horizon=30):
    data=torch.load(checkpoint_path,map_location='cpu',weights_only=False)
    actual_case=int(data['case'])
    if case is not None and actual_case!=case:raise ValueError('wrong model grid')
    agents=[]
    env=PredictiveACShield(actual_case,len(data['actors']),seed,'dim',horizon=horizon,shield=shield)
    obs=env.reset()
    for i,x in enumerate(obs):
        c=Agent(len(x),int(data['seed'])*100+i,hidden=128,latent=32,batch=256)
        c.actor.load_state_dict(data['actors'][i])
        c.critic.load_state_dict(data['critics'][i])
        agents.append(c)
    records=[];steps=[]
    for e in range(tests):
        test=PredictiveACShield(actual_case,len(agents),seed*10000+e,'dim',
                               horizon=horizon,shield=shield)
        o=test.reset();done=False;trace=[];dwell=0;safe_success=False
        while not done:
            a=[c.act(x,explore=False) for c,x in zip(agents,o)]
            o,_,done,info=test.step(a)
            dwell=dwell+1 if info['safe'] and info['restored_pct']>=90 else 0
            if dwell>=5:safe_success=True
            trace.append(info)
        records.append({'episode':e,'safe_dwell5':int(safe_success),
                        'mean_restored_pct':float(np.mean([x['restored_pct'] for x in trace])),
                        'final_restored_pct':float(trace[-1]['restored_pct']),
                        'unsafe_steps':sum(not x['safe'] for x in trace),
                        'candidate_feasible_steps':sum(x['feasible_candidate_found'] for x in test.shield_audit),
                        'shield_interventions':sum(x['enforced_action_change'] for x in test.shield_audit),
                        'contract_mismatch':sum(x['shield_contract_mismatch'] for x in test.shield_audit)})
        for k,(info,shield_info) in enumerate(zip(trace,test.shield_audit)):
            steps.append({'episode':e,'step':k+1,**info,**shield_info})
    out={'backend':'pandapower IEEE quasi-static AC','case':actual_case,'trained_seed':data['seed'],
         'method':data['method'],'shield_enabled':shield,'evaluation_seed':seed,
         'test_count':tests,'horizon':horizon,'scope':'hard pre-action simulation gate when feasible; infeasibility reported; no frequency guarantee',
         'safe_dwell5':sum(x['safe_dwell5'] for x in records),
         'total_unsafe_steps':sum(x['unsafe_steps'] for x in records),
         'total_action_interventions':sum(x['shield_interventions'] for x in records),
         'total_feasible_candidate_steps':sum(x['candidate_feasible_steps'] for x in records),
         'contract_mismatches':sum(x['contract_mismatch'] for x in records),
         'mean_final_load':float(np.mean([x['final_restored_pct'] for x in records])),
         'individual_tests':records,'per_step':steps}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--case',type=int,choices=[39,118],required=True)
    p.add_argument('--eval-seed',type=int,default=111)
    p.add_argument('--tests',type=int,default=10)
    p.add_argument('--horizon',type=int,default=30)
    p.add_argument('--shield',choices=['on','off'],default='on')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();torch.set_num_threads(1)
    d=frozen_evaluation(a.checkpoint,a.shield=='on',a.case,a.eval_seed,a.tests,a.horizon)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in d.items() if k not in ('per_step','individual_tests')}))
if __name__=='__main__':main()
