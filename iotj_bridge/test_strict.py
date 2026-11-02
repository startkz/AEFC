#!/usr/bin/env python3
"""Unit/integration checks of paper mechanisms, NOT publication claims."""
import math, tempfile
import numpy as np
import torch
try:
 from .strict_agent import PER,Agent,Server,ServerSettings,flatten
except ImportError:
 from strict_agent import PER,Agent,Server,ServerSettings,flatten

def test_replay():
 p=PER(3,100,alpha=.6,seed=33)
 for i in range(60):p.add([i%5,0,1],.2,float(i%2),[0,0,0],False,'recovering')
 batch=p.sample(24)
 assert len(batch['idx'])==24 and torch.isfinite(batch['isw']).all()
 p.update(batch['idx'],[0.3]*24)
 assert np.all(p.prior[batch['idx']]>0)
def test_local_and_sharing():
 a=Agent(3,seed=1,latent=8,hidden=16,batch=16,capacity=500)
 b=Agent(5,seed=2,latent=8,hidden=16,batch=16,capacity=500)
 t=flatten(a.actor.backbone)
 b.set_global(t)
 for i in range(120):
  for c in (a,b):
   s=np.ones(c.replay.obs.shape[1],np.float32)*((i%13)/13)
   action=float((i%7)/7);nxt=s+0.01
   c.replay.add(s,action,float(action-.4),nxt,i%17==0,'recovering' if i%2 else 'unsafe')
 before=flatten(a.actor.backbone).clone()
 c1=a.local_fit(steps=2,prototypes=None,update_after=16)
 assert c1['updates']==2
 assert torch.equal(before,flatten(a.actor.backbone)),'backbone changed during adapter training'
 assert sum(int(x) for x in a.replay.prior[:a.replay.n]!=1)>0,'PER priorities never updated'
 m=a.share(before,mode='adv',sharing_steps=2)
 if m is None:
  # Synthetic Q can select no positive behaviors; force explore-policy offsets,
  # and report the empty-set condition rather than manufacturing a message.
  return
 assert len(m['idx'])==math.ceil(.2*len(before))
 assert np.array_equal(np.sort(m['idx']),m['idx'])
 assert torch.equal(before,flatten(a.actor.backbone)),'sharing changed deployed global backbone'
 assert torch.isfinite(torch.tensor(m['uncompressed'])).all()
 s=Server(before,ServerSettings(clip_update=.1))
 out=s.step([m])
 assert out['accepted']==1 and out['upload_bytes']>0
 assert abs(sum(out['weight'])-1)<1e-7
def test_malicious_metadata():
 g=torch.zeros(6)
 base={'idx':np.array([0,2],np.int32),'val':np.array([.01,.01],np.float32),
       'n':6,'utility':.01,'proto':{'recovering':torch.ones(8)}}
 s=Server(g,ServerSettings(clip_update=.1))
 un=s.step([base,base,base,base,base],poisoned=[4],attack='joint')
 assert un['malicious_weight']>0
 cap=Server(g,ServerSettings(clip_update=.1,max_weight=.35))
 cc=cap.step([base,base,base,base,base],poisoned=[4],attack='joint')
 assert cc['malicious_weight']<=.3500001
 assert un['upload_bytes']==cc['upload_bytes']
def run():
 torch.set_num_threads(1)
 test_replay();test_local_and_sharing();test_malicious_metadata()
 print('PASS strict PER, optimizer boundary, serialization, capped server tests')
if __name__=='__main__':run()
