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
 from .strict_agent import Agent, Server, ServerSettings, flatten, serialized_size
 from .adaptive_attack import AdaptiveServer, ADAPTIVE_MODES
except ImportError:
 from run_experiment import Grid
 from strict_agent import Agent, Server, ServerSettings, flatten, serialized_size
 from adaptive_attack import AdaptiveServer, ADAPTIVE_MODES

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
  if self.hetero=='pad_dim':
   # Naive same-size zero padding for an explicit no-adapter control.
   for j in range(1,len(o),2):o[j][3:]=0.
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
  if self.hetero=='shift' and self.step_idx==11 and getattr(self,'demand_shift_enabled',True):
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
  client_demand=np.array([self.demand[g].sum() for g in self.groups],dtype=float)
  client_reference=np.array([self.original[g].sum() for g in self.groups],dtype=float)
  info={'restored_pct':restored,'safe':safe,'ac_converged':int(self.valid),
        'voltage_violation_pu_sum':self.voltage_excess,
        'thermal_excess_pct_sum':self.thermal_excess,
        'actuator_saturation':int(any((cmd<0)|(cmd>1))),
        'actual_steps':self.step_idx,
        'client_served_fraction':self.served.astype(float).tolist(),
        'client_demand_mw':client_demand.tolist(),
        'client_demand_ratio':(client_demand/client_reference).tolist()}
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
 local_served_paths=[[] for _ in agents]
 local_demand_ratios=[[] for _ in agents]
 rng=np.random.default_rng(noise_seed)
 while not done:
  a=[c.act(x,explore=explore,sigma=.15) for c,x in zip(agents,obs)]
  ns,rews,done,info=env.step(a)
  for i in range(len(agents)):
   local_served_paths[i].append(float(env.served[i]))
   local_demand_ratios[i].append(float(info['client_demand_ratio'][i]))
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
 client_outcomes=[]
 for i,path in enumerate(local_served_paths):
  values=np.asarray(path,dtype=float)
  reach=np.flatnonzero(values>=.90)
  client_outcomes.append({'client_id':i,
      'mean_served_fraction':float(values.mean()),
      'final_served_fraction':float(values[-1]),
      'first_90pct_step':int(reach[0]+1) if len(reach) else -1,
      'mean_demand_ratio':float(np.mean(local_demand_ratios[i])),
      'final_demand_ratio':float(local_demand_ratios[i][-1])})
 return {'final_restored_pct':end['restored_pct'],
         'average_restored_pct':float(np.mean([z['restored_pct'] for z in env.violations])),
         'safe_dwell5':int(first is not None),
         'recovery_step':-1 if first is None else first,
         'max_thermal_excess_pct':max(z['thermal_excess_pct_sum'] for z in env.violations),
         'max_voltage_violation_pu':max(z['voltage_violation_pu_sum'] for z in env.violations),
         'any_unsafe':int(any(not z['safe'] for z in env.violations)),
         'censored':int(first is None),'client_outcomes':client_outcomes,'trace':records}

def run(case,seed,mode='adv',hetero='base',attack='clean',episodes=10,
        clients_n=5,batch=256,hidden=128,latent=32,steps=5,
        sharing_steps=2,kappa=.2,eval_episodes=3,weight_cap=None,disable_proto=False,
        malicious_clients=1,disable_adapters=False,fixed_traffic=False,
        shift_lambda=1.0,attack_start_round=None,shift_onset_round=None,
        bytes_to_target_dir=None,attack_strength=1.0,record_training_trace=False):
 torch.set_num_threads(1);torch.manual_seed(seed);np.random.seed(seed)
 env=RecoveryGrid(case,clients_n,seed,hetero,attack='physical' if attack in ('physical','joint') else 'clean')
 observations=env.reset()
 agents=[]
 for i,obs in enumerate(observations):
  action_high=.6 if hetero=='saturation' and i%2 else 1.
  agents.append(Agent(len(obs),seed*100+i,latent=latent,hidden=hidden,
                      act_high=action_high,batch=batch))
 theta=flatten(agents[0].actor.backbone)
 settings=ServerSettings(max_weight=weight_cap,equal_weight=(mode=='adv_no_cw' or mode=='dense'),
                         shift_lambda=float(shift_lambda))
 server=(AdaptiveServer(theta,settings,strength=attack_strength)
         if attack in ADAPTIVE_MODES else Server(theta,settings))
 for c in agents:c.set_global(server.theta)
 first_record=[];traffic=0;server_summaries=[];train_episode_records=[]
 sync_interval=5
 rounds=math.ceil(episodes/sync_interval)
 btt=None
 if bytes_to_target_dir is not None:
  if mode=='critic_share':
   raise ValueError('Analytical critic_share byte estimates cannot be labeled measured bytes-to-target')
  try:
   from .bytes_to_target import ByteTargetTracker
  except ImportError:
   from bytes_to_target import ByteTargetTracker
  btt=ByteTargetTracker(bytes_to_target_dir,case,seed,mode,hetero,attack,clients_n,
      rounds,[len(x) for x in observations],fixed_traffic)
  btt.snapshot(0,agents,0,0)
 if shift_onset_round is not None and (hetero!='shift' or int(shift_onset_round)<0 or int(shift_onset_round)>rounds):
  raise ValueError('shift_onset_round only permits 0..scheduled_rounds with hetero=shift')
 for k in range(rounds):
  # Identity-preserving clean phase: observation and actor dimensions never change.
  env.demand_shift_enabled=bool(shift_onset_round is None or k>=int(shift_onset_round))
  for e in range(k*sync_interval,min((k+1)*sync_interval,episodes)):
   episode_result=run_episode(env,agents,True,noise_seed=seed*100000+e,trace=record_training_trace)
   ep_record={'episode':e+1,'average_restored_pct':episode_result['average_restored_pct'],
       'final_restored_pct':episode_result['final_restored_pct'],
       'safe_dwell5':episode_result['safe_dwell5'],'any_unsafe':episode_result['any_unsafe'],
       'max_thermal_excess_pct':episode_result['max_thermal_excess_pct'],
       'max_voltage_violation_pu':episode_result['max_voltage_violation_pu'],
       'censored':episode_result['censored'],
       'shift_active':int(hetero=='shift' and env.demand_shift_enabled),
       'client_outcomes':episode_result['client_outcomes']}
   if record_training_trace:
    ep_record.update({'recovery_step':episode_result['recovery_step'],
                      'recovery_accuracy_pct':episode_result['final_restored_pct'],
                      'steps_executed':len(env.violations),
                      'recovery_reached':episode_result['safe_dwell5'],
                      'trace':episode_result['trace']})
   train_episode_records.append(ep_record)
  out=[]
  for i,c in enumerate(agents):
   if mode!='critic_share':c.set_global(server.theta)
   c.local_fit(steps=steps,prototypes=server.prototypes,disable_proto=disable_proto,
               disable_adapter=disable_adapters,
               update_after=max(16,min(batch,128)))
   out.append(c.share(flatten(c.actor.backbone) if mode=='critic_share' else server.theta,
                      mode='adv' if mode=='adv_no_cw' else mode,kappa=kappa,
                      sharing_steps=sharing_steps,fixed_traffic=fixed_traffic))
  attack_modes=('poison','joint','delayed_joint','immediate_metadata','delayed_metadata',
                'immediate_credibility','delayed_credibility','temporal_credibility')+ADAPTIVE_MODES
  bad=tuple(range(clients_n-min(malicious_clients,clients_n),clients_n)) if attack in attack_modes else ()
  atk='joint' if attack in ('poison','joint') else (attack if attack in (
      'delayed_joint','immediate_metadata','delayed_metadata',
      'immediate_credibility','delayed_credibility','temporal_credibility')+ADAPTIVE_MODES else None)
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
   stats=server.step(out,poisoned=bad,attack=atk,round_id=k,
                     attack_start_round=attack_start_round)
   for a in agents:a.set_global(server.theta)
  traffic+=stats['upload_bytes']
  server_summaries.append({'round':k,'round_1based':k+1,'uplink_bytes':stats['upload_bytes'],
                           'malicious_weight':stats['malicious_weight'],'accepted':stats['accepted'],
                           'direction_norm':stats.get('direction_norm',0.),
                           'attack_active':stats.get('attack_active',False),
                           'shift_active':int(hetero=='shift' and env.demand_shift_enabled),
                           'attack_start_round_0based':stats.get('attack_start_round'),
                           'trained_episodes':min((k+1)*sync_interval,episodes),
                           'per_client':stats.get('per_client',[]),
                           'coordinate_selection':[
                               None if m is None else m.get('coordinate_selection_audit')
                               for m in out],
                           'actual_serialized_client_bytes':[
                               0 if m is None else serialized_size(m)
                               for m in out],
                           'attack_strength':stats.get('attack_strength',0.),
                           'attack_mode':stats.get('attack_mode',None),
                           'malicious_accepted_count':stats.get('malicious_accepted_count',0)})
  if btt is not None:
   btt.snapshot(k+1,agents,traffic,int(stats['upload_bytes']))
 btt_report=btt.finalize(agents,server_summaries) if btt is not None else None
 test_runs=[]
 for e in range(eval_episodes):
  # Fixed independent evaluation seeds are kept separate from training.
  test=RecoveryGrid(case,clients_n,100000+seed*100+e,hetero,
                    attack='joint' if attack=='joint' else 'physical' if attack=='physical' else 'clean')
  test_runs.append(run_episode(test,agents,False,noise_seed=1000000+seed*100+e,trace=True))
 summary={'backend':'pandapower AC quasi-static','case':case,'seed':seed,
          'method':mode,'hetero':hetero,'attack':attack,
          'attack_strength':float(attack_strength) if attack in ADAPTIVE_MODES else None,
          'attack_search_visibility':'prior model increments and prototypes, own preceding public weight only' if attack in ADAPTIVE_MODES else None,
          'coordinate_selection_rule':(
              'uniform_random_coordinate_without_replacement' if mode=='coord_random'
              else 'sum_abs_raw_pre_adam_gradients' if mode=='coord_gradtopk'
              else 'topk_final_adam_displacement' if mode in ('adv','ordinary') else None),
          'clients':clients_n,
          'malicious_clients':len(bad),'malicious_client_ids':list(bad),
          'attack_start_round_0based':attack_start_round,
          'attack_start_round_1based':None if attack_start_round is None else int(attack_start_round)+1,
          'shift_lambda':float(shift_lambda),
          'shift_onset_round_0based':shift_onset_round,
          'shift_onset_round_1based':None if shift_onset_round is None else shift_onset_round+1,
          'train_episodes':episodes,
          'scheduled_rounds':rounds,'completed_rounds':len(server_summaries),
          'train_episode_records':len(train_episode_records),
          'record_training_trace':int(record_training_trace),
          'train_recovery_rule':'first of 5 consecutive converged AC steps with >=90% load and zero voltage/thermal violation; -1 if not reached' if record_training_trace else None,
          'train_accuracy_rule':'final served load divided by demand, percent; not a recovery-success percentage' if record_training_trace else None,
          'randomized_load_profile':'rng(seed+901), new scenario per episode',
          'eval_episodes':eval_episodes,'steps_per_episode':env.horizon,
          'fed_sync_interval':sync_interval,'batch_size':batch,'hidden_size':hidden,
          'latent_size':latent,'per_alpha':.6,'per_beta':.4,
          'tau':.005,'gamma':.99,'kappa':kappa,'sharing_steps':sharing_steps,
          'local_fit_steps':steps,'weight_cap':str(weight_cap),
          'disable_proto':int(disable_proto),'disable_adapters':int(disable_adapters),
          'fixed_traffic':int(fixed_traffic),
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
 if btt_report is not None:
  summary['bytes_to_target_protocol']=btt_report['protocol_id']
  summary['bytes_to_target_joint_event_observed']=btt_report['joint_target']['event_observed']
  summary['bytes_to_target_joint_bytes']=btt_report['joint_target']['bytes_to_target']
  summary['bytes_to_target_load_only_bytes']=btt_report['load_only_target']['bytes_to_target']
 return summary,server_summaries,test_runs,train_episode_records,agents,server

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--case',type=int,choices=[39,118],required=True)
 p.add_argument('--seed',type=int,default=80)
 p.add_argument('--mode',choices=['adv','ordinary','random','td','uniform_high','dense','adv_no_cw','critic_share','dense_cw','coord_random','coord_gradtopk'],default='adv')
 p.add_argument('--hetero',choices=['base','dim','mask','delay','shift','saturation','attackgroup','pad_dim'],default='dim')
 p.add_argument('--attack',choices=['clean','physical','joint','poison','delayed_joint','immediate_metadata','delayed_metadata','immediate_credibility','delayed_credibility','temporal_credibility',*ADAPTIVE_MODES],default='clean')
 p.add_argument('--attack-strength',type=float,default=1.,help='Adaptive manipulation budget in [0,2]')
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
 p.add_argument('--disable-adapters',action='store_true')
 p.add_argument('--fixed-traffic',action='store_true')
 p.add_argument('--record-training-trace',action='store_true',help='Immutable per-episode step trace and first safe five-step dwell; logging only')
 p.add_argument('--malicious-clients',type=int,default=1)
 p.add_argument('--shift-lambda',type=float,default=1.0)
 p.add_argument('--attack-start-round',type=int,default=None)
 p.add_argument('--shift-onset-round',type=int,default=None)
 p.add_argument('--out',type=Path,required=True)
 p.add_argument('--bytes-to-target-dir',type=Path,default=None,
                help='Optional per-round frozen actor checkpoints, fixed validation and independent test')
 args=p.parse_args()
 result,rounds,tests,train_episode_records,agents,server=run(args.case,args.seed,args.mode,args.hetero,args.attack,
     args.episodes,args.clients,args.batch,args.hidden,args.latent,args.local_steps,
     args.sharing_steps,args.kappa,args.eval_episodes,args.weight_cap,args.disable_proto,
     args.malicious_clients,args.disable_adapters,args.fixed_traffic,args.shift_lambda,
     args.attack_start_round,args.shift_onset_round,args.bytes_to_target_dir,args.attack_strength,args.record_training_trace)
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps({'summary':result,'rounds':rounds,'tests':tests,
                                'train_episodes':train_episode_records},
                                indent=None if args.record_training_trace else 2,
                                separators=(',',':') if args.record_training_trace else None,
                                allow_nan=False)+'\n')
 import os,hashlib,sys
 ckpt=args.out.with_suffix('.pt')
 torch.save({'seed':args.seed,'method':args.mode,'case':args.case,
             'server_theta':server.theta,'server_prototypes':server.prototypes,
             'actors':[c.actor.state_dict() for c in agents],
             'critics':[c.critic.state_dict() for c in agents],
             'target_actors':[c.target_actor.state_dict() for c in agents],
             'target_critics':[c.target_critic.state_dict() for c in agents],
             'actor_adapter_optimizers':[c.adapter_opt.state_dict() for c in agents],
             'critic_optimizers':[c.critic_opt.state_dict() for c in agents],
             'replay_priorities':[c.replay.prior[:c.replay.n].copy() for c in agents],
             'per_rng_states':[c.replay.rng.bit_generator.state for c in agents],
             'commit_sha':os.getenv('GITHUB_SHA','unavailable')},ckpt)
 digest=hashlib.sha256(ckpt.read_bytes()).hexdigest()
 metadata={'git_commit':os.getenv('GITHUB_SHA','unavailable'),
          'github_run_id':os.getenv('GITHUB_RUN_ID','unavailable'),
          'python':sys.version.split()[0],
          'torch':torch.__version__,
          'checkpoint_sha256':digest,'checkpoint_path':ckpt.name,
          'source_json_sha256':hashlib.sha256(args.out.read_bytes()).hexdigest(),
          'training_episodes_executed':result['train_episodes']}
 args.out.with_suffix('.manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
 print(json.dumps(result))
if __name__=='__main__':main()
