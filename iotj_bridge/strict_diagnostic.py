#!/usr/bin/env python3
"""Mechanism-level fixed-surrogate diagnostics for strict PER-AEFC implementation.
Empirical minibatch bias and variance, not a theoretical uniform bound.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
import torch
from torch import nn
try:
 from .strict_agent import Agent,Server,ServerSettings,flatten
 from .strict_run import RecoveryGrid,run_episode
except ImportError:
 from strict_agent import Agent,Server,ServerSettings,flatten
 from strict_run import RecoveryGrid,run_episode

def full_reference(agent,limit=2048):
 p=agent.replay
 if not len(p):return None
 ids=np.arange(max(0,p.n-limit),p.n)
 s=torch.tensor(p.obs[ids],dtype=torch.float32);a=torch.tensor(p.act[ids])
 with torch.no_grad():
  q0=agent.critic(torch.cat((s,a),-1)).flatten()
  q1=agent.critic(torch.cat((s,agent.actor(s)),-1)).flatten()
  advantage=q0-q1
  select=advantage>0
  prob=np.maximum(p.prior[:p.n],1e-10)**p.alpha;prob/=prob.sum()
  v=(p.n*prob[ids])**(-p.beta0)
  v/=max(v.max(),1e-12)
  v=torch.as_tensor(v,dtype=torch.float32)
  weight=(advantage[select]*v[select]).detach()
 if int(select.sum())==0 or float(weight.sum())<=0:return None
 weight=weight/weight.sum()
 q=agent.critic(torch.cat((s[select],agent.actor(s[select])),-1)).flatten()
 loss=-(weight*q).sum()
 grads=torch.autograd.grad(loss,list(agent.actor.backbone.parameters()))
 return torch.cat([g.detach().flatten() for g in grads]).numpy()

def diagnostic(case=39,seed=80,episodes=10,draws=16,hidden=32,latent=16,batch=32):
 torch.set_num_threads(1)
 np.random.seed(seed);torch.manual_seed(seed)
 env=RecoveryGrid(case,5,seed,'dim',attack='clean',horizon=30)
 obs=env.reset()
 agents=[Agent(len(o),seed*100+i,hidden=hidden,latent=latent,batch=batch) for i,o in enumerate(obs)]
 server=Server(flatten(agents[0].actor.backbone),ServerSettings())
 for c in agents:c.set_global(server.theta)
 for round_id in range(math.ceil(episodes/5)):
  for episode in range(round_id*5,min(episodes,(round_id+1)*5)):
   run_episode(env,agents,True,seed*100+episode)
  messages=[]
  for c in agents:
   c.set_global(server.theta)
   c.local_fit(steps=5,prototypes=server.prototypes,update_after=max(16,min(batch,128)))
   messages.append(c.share(server.theta,sharing_steps=2))
  server.step(messages,round_id=round_id)
  for c in agents:c.set_global(server.theta)
 # Freeze critic and adapters and replay at the end of training.
 refs=[full_reference(a) for a in agents]
 if any(r is None for r in refs):
  return {'case':case,'seed':seed,'status':'missing-positive-reference-gradient',
          'has_reference':[x is not None for x in refs]}
 reference=np.mean(refs,axis=0)
 results=[]
 scale=2*.001
 for j in range(draws):
  messages=[c.share(server.theta,sharing_steps=2) for c in agents]
  if any(x is None for x in messages):continue
  dense=np.mean([m['uncompressed'] for m in messages],axis=0)
  sparse=[];clipped=[]
  for m in messages:
   v=np.zeros_like(dense);v[m['idx']]=m['val'];sparse.append(v)
   clipped.append(v*min(1.,.075/(np.linalg.norm(v)+1e-12)))
  unweighted=np.mean(sparse,axis=0)
  cmean=np.mean(clipped,axis=0)
  trial=Server(server.theta,ServerSettings())
  trial.prototypes={k:x.clone() for k,x in server.prototypes.items()}
  outcome=trial.step(messages)
  final=outcome['direction'].numpy()
  results.append({'direction':-final/scale,
    'adam_delta':(-dense/scale-reference),
    'topk_delta':(-unweighted+dense)/scale,
    'clip_delta':(-cmean+unweighted)/scale,
    'weight_delta':(-final+cmean)/scale})
 if len(results)<2:return {'case':case,'seed':seed,'status':'insufficient-nonempty-samples','draws':len(results)}
 d=np.stack([x['direction'] for x in results],axis=0)
 report={'case':case,'seed':seed,'status':'ok','episodes':episodes,'draws':len(results),
  'actual_backbone_params':int(len(server.theta)),
  'reference_gradient_l2':float(np.linalg.norm(reference)),
  'estimated_bias_l2':float(np.linalg.norm(d.mean(axis=0)-reference)),
  'estimated_variance_trace':float(np.var(d,axis=0,ddof=1).sum()),
  'direction_cosine_to_reference':float(np.dot(d.mean(0),reference)/
       (np.linalg.norm(d.mean(0))*np.linalg.norm(reference)+1e-12)),
  'direction_scale':'-Delta/(2*actor_lr), not exact Adam gradient',
  'assumptions':'critic, adapters, PER priorities and replay held fixed during repeated sharing calls'}
 for label in ('adam_delta','topk_delta','clip_delta','weight_delta'):
  report[label+'_mean_l2']=float(np.mean([np.linalg.norm(x[label]) for x in results]))
 return report

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--case',type=int,choices=[39,118],required=True)
 p.add_argument('--seed',type=int,default=80)
 p.add_argument('--episodes',type=int,default=10)
 p.add_argument('--draws',type=int,default=16)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 r=diagnostic(a.case,a.seed,a.episodes,a.draws)
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r))
 if r['status']!='ok':raise SystemExit(2)
if __name__=='__main__':main()
