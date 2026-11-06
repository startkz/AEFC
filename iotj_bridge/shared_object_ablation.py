#!/usr/bin/env python3
"""Controlled actor-vs-critic shared-object experiment on the original IEEE AC task.

Both arms use exactly the same local PER-DDPG Agent, actor/critic networks,
local_fit() and advantage-conditioned local actor step (Agent.share()).
Only the synchronized parameter block differs: actor.backbone vs critic[2:].
The critic first layer stays private so heterogeneous observation dimensions
remain supported. This is an architectural intervention, NOT A2FC reproduction.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,sys
from pathlib import Path
import numpy as np
import torch
try:
 from .strict_run import RecoveryGrid,run_episode
 from .strict_agent import Agent,Server,ServerSettings,flatten,set_flat,serialized_size
except ImportError:
 from strict_run import RecoveryGrid,run_episode
 from strict_agent import Agent,Server,ServerSettings,flatten,set_flat,serialized_size


def obj_hash(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def run(args):
 if args.episodes%5:raise ValueError('episodes must be divisible by 5')
 if not args.fixed_traffic:raise ValueError('This protocol requires actual fixed-size serialized uplink messages')
 torch.set_num_threads(1);torch.manual_seed(args.seed);np.random.seed(args.seed)
 env=RecoveryGrid(args.case,args.clients,args.seed,args.hetero,
                  attack='physical' if args.attack=='joint' else 'clean')
 obs=env.reset()
 agents=[Agent(len(o),args.seed*100+i,latent=args.latent,hidden=args.hidden,batch=args.batch)
         for i,o in enumerate(obs)]
 # Both arms begin from the IDENTICAL shared actor-backbone state.
 actor_init=flatten(agents[0].actor.backbone).clone()
 actor_dim=int(actor_init.numel())
 critic_blocks=[a.critic[2:] for a in agents]
 critic_initial=flatten(critic_blocks[0]).clone()
 critic_dim=int(critic_initial.numel())
 # Top-k coordinates are matched by absolute cardinality, not by percentage:
 # the shared object dimensions differ. Actual serialized bytes are checked.
 k_absolute=max(1,int(math.ceil(args.kappa*actor_dim)))
 if k_absolute>critic_dim:
  raise ValueError('Shared critic compatible block too small for equal Top-k coordinate budget')
 settings=ServerSettings(equal_weight=(args.component=='no_cred'))
 server=Server(actor_init if args.architecture=='actor' else critic_initial,settings)
 for a,block in zip(agents,critic_blocks):
  a.set_global(actor_init)
  set_flat(block,critic_initial)
  a.polyak(block,a.target_critic[2:])
 all_rounds=[];training=[];cumulative=0
 for r in range(args.episodes//5):
  for ep in range(r*5,(r+1)*5):
   outcome=run_episode(env,agents,True,noise_seed=args.seed*100000+ep)
   training.append({'episode_1based':ep+1,
                    'average_restored_pct':outcome['average_restored_pct'],
                    'final_restored_pct':outcome['final_restored_pct'],
                    'safe_dwell5':int(outcome['safe_dwell5']),
                    'any_unsafe':int(outcome['any_unsafe'])})
  messages=[]
  for a,critic_block in zip(agents,critic_blocks):
   if args.architecture=='actor':
    a.set_global(server.theta)
   else:
    # Exactly the compatible critic subblock is globally synchronized.
    # The observation-dependent first critic layer remains personalized.
    set_flat(critic_block,server.theta)
    a.polyak(critic_block,a.target_critic[2:])
   a.local_fit(steps=args.local_steps,prototypes=server.prototypes,
               disable_proto=(args.component=='no_proto'),
               update_after=max(16,min(args.batch,128)))
   if args.architecture=='actor':
    m=a.share(server.theta,mode='ordinary' if args.component=='no_adv' else 'adv',
              kappa=args.kappa,sharing_steps=args.sharing_steps,fixed_traffic=True)
   else:
    # Local actor receives the SAME advantage-conditioned update but keeps it
    # private. Message metadata is identical to the actor arm.
    local_actor_base=flatten(a.actor.backbone).clone()
    m=a.share(local_actor_base,mode='ordinary' if args.component=='no_adv' else 'adv',
              kappa=args.kappa,sharing_steps=args.sharing_steps,fixed_traffic=True)
    if m is None:raise ValueError('Fixed-traffic local actor message unexpectedly missing')
    set_flat(a.actor.backbone,local_actor_base+
             torch.as_tensor(m['uncompressed'],dtype=torch.float32))
    a.polyak(a.actor.backbone,a.target_actor.backbone)
    # Transmit actual sparse critic subblock update at exactly the same
    # absolute Top-k coordinate budget as the actor arm.
    d=flatten(critic_block)-server.theta
    choose=torch.argsort(d.abs(),descending=True,stable=True)[:k_absolute].sort().values
    m['idx']=choose.numpy().astype(np.int32)
    m['val']=d[choose].numpy().astype(np.float32)
    m['n']=critic_dim
    m['uncompressed']=d.numpy().astype(np.float32)
   if m is None:raise ValueError('Fixed-traffic message unexpectedly missing')
   if int(len(m['idx']))!=k_absolute:
    raise ValueError('Top-k coordinate count not equal across sharing arms')
   messages.append(m)
  # Attack exposure, clipping, prototype processing and credibility scoring
  # are the SAME Server.step implementation for both shared objects.
  expected_bytes=sum(serialized_size(m) for m in messages)
  bad=(args.clients-1,) if args.attack=='joint' else ()
  stats=server.step(messages,poisoned=bad,attack='joint' if bad else None,round_id=r)
  if int(stats['upload_bytes'])!=expected_bytes:
   raise ValueError(f'Serialized traffic mismatch at round {r+1}: {stats["upload_bytes"]} vs {expected_bytes}')
  for a,block in zip(agents,critic_blocks):
   if args.architecture=='actor':
    a.set_global(server.theta)
   else:
    set_flat(block,server.theta)
    a.polyak(block,a.target_critic[2:])
  cumulative+=int(stats['upload_bytes'])
  all_rounds.append({
   'round_1based':r+1,'training_episodes':min((r+1)*5,args.episodes),
   'uplink_bytes':int(stats['upload_bytes']),
   'cumulative_uplink_bytes':cumulative,
   'expected_serialized_bytes_before_attack':expected_bytes,
   'accepted':int(stats['accepted']),
   'malicious_weight':float(stats['malicious_weight']),
   'attack_active':bool(stats.get('attack_active',False)),
   'topk_coordinates_per_client':k_absolute,
   'per_client':stats.get('per_client',[])
  })
 test_runs=[]
 for e in range(args.eval_episodes):
  test=RecoveryGrid(args.case,args.clients,100000+args.seed*100+e,args.hetero,
                    attack='joint' if args.attack=='joint' else 'clean')
  result=run_episode(test,agents,False,noise_seed=1000000+args.seed*100+e,trace=True)
  result['test_seed']=100000+args.seed*100+e
  test_runs.append(result)
 summary={
  'protocol':'controlled-share-object-v1',
  'independent_unit':'training seed',
  'backend':'pandapower quasi-static AC (no dynamic frequency claim)',
  'architecture':args.architecture,'shared_object':
   'actor.backbone' if args.architecture=='actor' else 'critic.layers_2_and_4',
  'private_components':('actor.encoder+actor.head+whole critic' if args.architecture=='actor'
                        else 'whole actor+critic input layer'),
  'component':args.component,'case':args.case,'seed':args.seed,
  'attack':args.attack,'hetero':args.hetero,'clients':args.clients,
  'malicious_clients':1 if args.attack=='joint' else 0,
  'episodes':args.episodes,'completed_rounds':len(all_rounds),
  'synchronization_interval_episodes':5,
  'eval_episodes':args.eval_episodes,
  'local_per_critic_updates_per_round':args.local_steps,
  'local_advantage_actor_updates_per_round':args.sharing_steps,
  'batch':args.batch,'hidden':args.hidden,'latent':args.latent,
  'kappa_reference':args.kappa,'k_coordinates_equal_across_arms':k_absolute,
  'actor_shared_params':actor_dim,'critic_compatible_shared_params':critic_dim,
  'same_actor_init_from_client_0':True,
  'fixed_traffic':True,
  'message_compression':'exact Top-k index/value float32+int32 with fixed serialized prototype padding',
  'uplink_measurement':'constructed serialized application payload, not socket or wire traffic',
  'total_measured_uplink_bytes':cumulative,
  'safe_dwell5_successes':sum(int(z['safe_dwell5']) for z in test_runs),
  'mean_final_restored_pct':float(np.mean([z['final_restored_pct'] for z in test_runs])),
  'mean_load_auc_pct':float(np.mean([z['average_restored_pct'] for z in test_runs])),
  'any_unsafe_tests':sum(int(z['any_unsafe']) for z in test_runs),
  'mean_malicious_weight':float(np.mean([z['malicious_weight'] for z in all_rounds])),
  'code_commit_sha':os.environ.get('GITHUB_SHA','unavailable'),
  'architecture_scope_note':
    'Both arms execute the same local PER-DDPG and actor advantage update. '
    'The critic arm transmits Top-k critic compatible-core deltas and retains local actors. '
    'Different actor and critic gradient dynamics remain a mechanism-level interpretation limitation. '
    'This is NOT an implementation of the published A2FC algorithm.'
 }
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps({'summary':summary,'rounds':all_rounds,
            'train_episodes':training,'tests':test_runs},allow_nan=False,indent=2)+'\n')
 ckpt=args.out.with_suffix('.pt')
 torch.save({'summary':summary,'actors':[a.actor.state_dict() for a in agents],
             'critics':[a.critic.state_dict() for a in agents],
             'server_shared_parameters':server.theta,
             'server_prototypes':server.prototypes},ckpt)
 manifest={
  'run_json_sha256':obj_hash(args.out),'checkpoint_sha256':obj_hash(ckpt),
  'checkpoint_file':ckpt.name,'github_run_id':os.environ.get('GITHUB_RUN_ID','unavailable'),
  'github_sha':os.environ.get('GITHUB_SHA','unavailable'),
  'python':sys.version.split()[0],'torch':torch.__version__,
  'pandapower':__import__('pandapower').__version__,
  'topk_k':k_absolute,'total_uplink_bytes':cumulative,
  'budget':{'episodes':args.episodes,'rounds':args.episodes//5,'heldout':args.eval_episodes}}
 args.out.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(summary,allow_nan=False))


def main():
 p=argparse.ArgumentParser()
 p.add_argument('--architecture',choices=['actor','critic'],required=True)
 p.add_argument('--component',choices=['full','no_adv','no_proto','no_cred'],required=True)
 p.add_argument('--attack',choices=['clean','joint'],required=True)
 p.add_argument('--case',type=int,choices=[39,118],default=39)
 p.add_argument('--seed',type=int,required=True)
 p.add_argument('--hetero',choices=['base','dim'],default='dim')
 p.add_argument('--clients',type=int,default=5)
 p.add_argument('--episodes',type=int,default=1000)
 p.add_argument('--eval-episodes',type=int,default=10)
 p.add_argument('--batch',type=int,default=256)
 p.add_argument('--hidden',type=int,default=128)
 p.add_argument('--latent',type=int,default=32)
 p.add_argument('--local-steps',type=int,default=5)
 p.add_argument('--sharing-steps',type=int,default=2)
 p.add_argument('--kappa',type=float,default=.2)
 p.add_argument('--fixed-traffic',action='store_true',required=True)
 p.add_argument('--out',type=Path,required=True)
 args=p.parse_args();run(args)

if __name__=='__main__':main()
