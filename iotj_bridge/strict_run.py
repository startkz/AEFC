"""AEFC-FRL cross-layer IEEE AC restoration experiment.

Quasi-static pandapower 39/118 electrical models; no rotor-frequency dynamics.
Fixed training seeds separate from held-out evaluation; no raw trajectory uploads.
"""
from __future__ import annotations
import argparse,csv,json,math,hashlib,platform
from pathlib import Path
import numpy as np
import torch
try:
 from .run_experiment import Grid
 from .strict_agent import Agent, Server, ServerSettings, flatten
except ImportError:
 from run_experiment import Grid
 from strict_agent import Agent, Server, ServerSettings, flatten

class RecoveryGrid(Grid):
 def __init__(self,case,clients,seed,hetero,attack='clean',horizon=30):
  self.attack=attack;self.horizon=int(horizon);self.obs_cache={};self.violations=[]
  self.rng=np.random.default_rng(seed+901)
  super().__init__(case,clients,seed,hetero)
 def reset(self):
  self.served=np.full(self.clients,.65)
  self.net.load.loc[:,'scaling']=.65
  # Draw a new operational demand profile for each episode from a seeded RNG.
  # Test environments have non-overlapping seeds and profiles.
  self.demand=self.original*np.clip(self.rng.normal(1.,.025,len(self.original)),.92,1.08)
  self.net.load.loc[:,'p_mw']=self.demand
  self.step_idx=0;self.obs_cache={};self.violations=[];self._delay_history=[]
  self._solve();return self.observations()
 def observations(self):
  if self.hetero in ('delay','shift'):
   saved=self.hetero;self.hetero='base';o=super().observations();self.hetero=saved
  else:o=super().observations()
  if self.hetero=='delay':
   # Exact 2-step stale local measurements, not fabricated constant voltage.
   history=getattr(self,'_delay_history',[])
   out=[x.copy() for x in o]
   for j in range(1,len(out),2):
    if len(history)>=2:out[j][1:4]=history[-2][j][1:4]
   history.append([x.copy() for x in o]);self._delay_history=history[-4:]
   o=out
  # Honest distribution shift in the plant is not labeled malicious.
  # Sensing attack is confined to local observation and never changes the true AC solver.
  if self.attack in ('physical','joint') and 5<=self.step_idx<16:
   target=0 if self.hetero=='attackgroup' else len(o)-1
   o[target]=o[target].copy()
   if len(o[target])>1:o[target][1]+=0.12
   if len(o[target])>2:o[target][2]-=0.09
  return o
 def step(self,actions):
  cmd=np.asarray(actions,float).copy()
  if self.hetero=='saturation':cmd[1::2]=np.minimum(cmd[1::2],.6)
  # Command corruption AFTER policy choice, evaluated against true physical state.
  if self.attack in ('physical','joint') and 5<=self.step_idx<16:
   target=0 if self.hetero=='attackgroup' else len(cmd)-1
   cmd[target]=np.clip(cmd[target]-.25,0,1)
  old=self.served.copy()
  if self.hetero=='shift' and self.step_idx==11:
   # An unannounced legitimate 6% load demand step, preserving continuity of control.
   for group in self.groups[1::2]:
    self.demand[group]*=1.06
   self.net.load.loc[:,'p_mw']=self.demand
  self.served=np.clip(old+.018*np.clip(cmd,0,1),0,1)
  for i,group in enumerate(self.groups):
   self.net.load.iloc[group,self.net.load.columns.get_loc('scaling')]=self.served[i]
  self.step_idx+=1;self._solve()
  demand=np.array([self.demand[g].sum() for g in self.groups])
  restored=100*float(np.dot(demand,self.served)/self.demand.sum())
  safe=bool(self.valid and self.thermal_excess<=1.e-7 and self.voltage_excess<=1.e-7)
  if not self.valid:cost=10.
  else:cost=min(10.,.02*self.thermal_excess+.1*self.voltage_excess)
  # Per-client rewards only use local served fraction and public operator safety alert.
  reward=[float(self.served[i] + 2*(self.served[i]-old[i])-cost-.004*cmd[i]**2)
          for i in range(self.clients)]
  info={'restored_pct':restored,'safe':safe,'ac_converged':int(self.valid),
        'voltage_violation_pu_sum':self.voltage_excess,
        'thermal_excess_pct_sum':self.thermal_excess,
        'actuator_saturation':int(any((cmd<0)|(cmd>1))),
        'actual_steps':self.step_idx}
  self.violations.append(info)
  return self.observations(),reward,self.step_idx>=self.horizon or not self.valid,info

def category_label(previous,now,eps_safe=.005,eps_progress=.0001):
 # Combined safety-alert/load deficit proxy: labels are local training labels,
 # not the global recovery success metric.
 phi=(max(0.,90-now['restored_pct'])/90+
      min(10.,now['thermal_excess_pct_sum'])/10.+
      now['voltage_violation_pu_sum'])
 if phi<=eps_safe:return 'stable'
 if previous is not None and phi < previous-eps_progress:return 'recovering'
 return 'unsafe'

def run_episode(env,agents,explore,noise_seed,trace=False):
 obs=env.reset();prev=None;records=[];dwell=0;first=None;done=False
 rng=np.random.default_rng(noise_seed)
 while not done:
  a=[c.act(x,explore=explore,sigma=.15) for c,x in zip(agents,obs)]
  ns,rews,done,info=env.step(a)
  cat=category_label(prev,info)
  prev=max(0.,90-info['restored_pct'])/90+min(10.,info['thermal_excess_pct_sum'])/10.+info['voltage_violation_pu_sum']
  if explore:
   for i,c in enumerate(agents):
    # Labels are computed from the client's own served-load trajectory and
    # the public AC safety alert; neither joint trajectories nor attack IDs are used.
    local_served=float(env.served[i])
    prior_served=float(obs[i][0])
    local_label=('stable' if info['safe'] and local_served>=.90
                 else 'recovering' if local_served-prior_served>1.e-4 and info['ac_converged']
                 else 'unsafe')
    c.replay.add(obs[i],a[i],rews[i],ns[i],done,local_label)
  dwell=dwell+1 if info['safe'] and info['restored_pct']>=90 else 0
  if dwell>=5 and first is None:first=env.step_idx-4
  if trace:records.append({'t':env.step_idx,**info,'recovery_label':cat})
  obs=ns
 end=env.violations[-1]
 return {'final_restored_pct':end['restored_pct'],
         'average_restored_pct':float(np.mean([z['restored_pct'] for z in env.violations])),
         'safe_dwell5':int(first is not None),
         'recovery_step':-1 if first is None else first,
         'max_thermal_excess_pct':max(z['thermal_excess_pct_sum'] for z in env.violations),
         'max_voltage_violation_pu':max(z['voltage_violation_pu_sum'] for z in env.violations),
         'any_unsafe':int(any(not z['safe'] for z in env.violations)),
         'censored':int(first is None),'trace':records}

def run(case,seed,mode='adv',hetero='base',attack='clean',episodes=10,
        clients_n=5,batch=256,hidden=128,latent=32,steps=5,
        sharing_steps=2,kappa=.2,eval_episodes=3,weight_cap=None,disable_proto=False,
        malicious_clients=1):
 torch.set_num_threads(1);torch.manual_seed(seed);np.random.seed(seed)
 env=RecoveryGrid(case,clients_n,seed,hetero,attack='physical' if attack in ('physical','joint') else 'clean')
 observations=env.reset()
 agents=[]
 for i,obs in enumerate(observations):
  action_high=.6 if hetero=='saturation' and i%2 else 1.
  agents.append(Agent(len(obs),seed*100+i,latent=latent,hidden=hidden,
                      act_high=action_high,batch=batch))
 theta=flatten(agents[0].actor.backbone)
 settings=ServerSettings(max_weight=weight_cap,equal_weight=(mode=='adv_no_cw' or mode=='dense'))
 server=Server(theta,settings)
 for c in agents:c.set_global(server.theta)
 first_record=[];traffic=0;server_summaries=[]
 sync_interval=5
 rounds=math.ceil(episodes/sync_interval)
 for k in range(rounds):
  for e in range(k*sync_interval,min((k+1)*sync_interval,episodes)):
   run_episode(env,agents,True,noise_seed=seed*100000+e)
  out=[]
  for i,c in enumerate(agents):
   if mode!='critic_share':c.set_global(server.theta)
   c.local_fit(steps=steps,prototypes=server.prototypes,disable_proto=disable_proto,
               update_after=max(16,min(batch,128)))
   out.append(c.share(flatten(c.actor.backbone) if mode=='critic_share' else server.theta,
                      mode='adv' if mode=='adv_no_cw' else mode,kappa=kappa,
                      sharing_steps=sharing_steps))
  bad=tuple(range(clients_n-min(malicious_clients,clients_n),clients_n)) if attack in ('poison','joint','delayed_joint') else ()
  atk='joint' if attack in ('poison','joint') else ('delayed_joint' if attack=='delayed_joint' else None)
  if mode=='critic_share':
   # A2FC-inspired architectural control: only critic weights are pooled.
   # Local actor backbones remain personalized, unlike AEFC-FRL. This is NOT
   # a faithful reproduction of the original A2C-specific A2FC algorithm.
   from strict_agent import set_flat as _set_flat,flatten as _flatten
   import torch as _torch
   avg=_torch.stack([_flatten(a.critic) for a in agents]).mean(0)
   for a,m in zip(agents,out):
    if m is not None:_set_flat(a.actor.backbone,_flatten(a.actor.backbone)+_torch.from_numpy(m['uncompressed']))
    _set_flat(a.critic,avg)
   stats={'upload_bytes':sum(_flatten(a.critic).numel()*4 for a in agents),
          'malicious_weight':0.,'accepted':len([m for m in out if m is not None])}
  else:
   stats=server.step(out,poisoned=bad,attack=atk,round_id=k)
   for a in agents:a.set_global(server.theta)
  traffic+=stats['upload_bytes']
  server_summaries.append({'round':k,'uplink_bytes':stats['upload_bytes'],
                           'malicious_weight':stats['malicious_weight'],'accepted':stats['accepted'],
                           'trained_episodes':min((k+1)*sync_interval,episodes)})
 test_runs=[]
 for e in range(eval_episodes):
  # Fixed independent evaluation seeds are kept separate from training.
  test=RecoveryGrid(case,clients_n,100000+seed*100+e,hetero,
                    attack='joint' if attack=='joint' else 'physical' if attack=='physical' else 'clean')
  test_runs.append(run_episode(test,agents,False,noise_seed=1000000+seed*100+e,trace=True))
 summary={'backend':'pandapower AC quasi-static','case':case,'seed':seed,
          'method':mode,'hetero':hetero,'attack':attack,'clients':clients_n,
          'malicious_clients':len(bad),'train_episodes':episodes,
          'scheduled_rounds':rounds,'completed_rounds':len(server_summaries),
          'eval_episodes':eval_episodes,'steps_per_episode':env.horizon,
          'fed_sync_interval':sync_interval,'batch_size':batch,'hidden_size':hidden,
          'latent_size':latent,'per_alpha':.6,'per_beta':.4,
          'tau':.005,'gamma':.99,'kappa':kappa,'sharing_steps':sharing_steps,
          'local_fit_steps':steps,'weight_cap':str(weight_cap),
          'disable_proto':int(disable_proto),
          'critic_traffic_scope':'analytic dense critic parameter payload (not serialized)' if mode=='critic_share' else 'measured application payload',
          'mean_test_load_pct':float(np.mean([v['final_restored_pct'] for v in test_runs])),
          'mean_test_load_auc_pct':float(np.mean([v['average_restored_pct'] for v in test_runs])),
          'safe_dwell_successes':sum(v['safe_dwell5'] for v in test_runs),
          'test_count':len(test_runs),
          'any_unsafe_count':sum(v['any_unsafe'] for v in test_runs),
          'max_thermal_excess':max(v['max_thermal_excess_pct'] for v in test_runs),
          'max_voltage_violation':max(v['max_voltage_violation_pu'] for v in test_runs),
          'uplink_bytes':traffic,
          'mean_malicious_weight':float(np.mean([x['malicious_weight'] for x in server_summaries]))}
 return summary,server_summaries,test_runs

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--case',type=int,choices=[39,118],required=True)
 p.add_argument('--seed',type=int,default=80)
 p.add_argument('--mode',choices=['adv','ordinary','random','td','uniform_high','dense','adv_no_cw','critic_share'],default='adv')
 p.add_argument('--hetero',choices=['base','dim','mask','delay','shift','saturation','attackgroup'],default='dim')
 p.add_argument('--attack',choices=['clean','physical','joint','poison','delayed_joint'],default='clean')
 p.add_argument('--episodes',type=int,default=10)
 p.add_argument('--clients',type=int,default=5)
 p.add_argument('--batch',type=int,default=256)
 p.add_argument('--hidden',type=int,default=128)
 p.add_argument('--latent',type=int,default=32)
 p.add_argument('--local-steps',type=int,default=5)
 p.add_argument('--sharing-steps',type=int,default=2)
 p.add_argument('--kappa',type=float,default=.2)
 p.add_argument('--eval-episodes',type=int,default=3)
 p.add_argument('--weight-cap',type=float,default=None)
 p.add_argument('--disable-proto',action='store_true')
 p.add_argument('--malicious-clients',type=int,default=1)
 p.add_argument('--out',type=Path,required=True)
 args=p.parse_args()
 result,rounds,tests=run(args.case,args.seed,args.mode,args.hetero,args.attack,
     args.episodes,args.clients,args.batch,args.hidden,args.latent,args.local_steps,
     args.sharing_steps,args.kappa,args.eval_episodes,args.weight_cap,args.disable_proto,args.malicious_clients)
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps({'summary':result,'rounds':rounds,'tests':tests},
                                indent=2,allow_nan=False)+'\n')
 print(json.dumps(result))
if __name__=='__main__':main()
