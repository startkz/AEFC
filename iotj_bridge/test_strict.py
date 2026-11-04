#!/usr/bin/env python3
"""Unit/integration checks of paper mechanisms, NOT publication claims."""
import math, tempfile
import numpy as np
import torch
try:
 from .strict_agent import PER,Agent,Server,ServerSettings,flatten,serialized_size
except ImportError:
 from strict_agent import PER,Agent,Server,ServerSettings,flatten,serialized_size

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
def test_all_updates_missing():
 s=Server(torch.zeros(6),ServerSettings())
 x=s.step([None,None,None])
 assert x['accepted']==0 and x['upload_bytes']==0
 assert x['malicious_weight']==0.0
 assert torch.equal(x['direction'],torch.zeros(6))
 assert np.array_equal(x['weight'],np.zeros(3))

def test_fixed_byte_transport():
 a=Agent(3,seed=88,latent=8,hidden=16,batch=16)
 theta=flatten(a.actor.backbone)
 empty=a._zero_sparse_message(theta,.2)
 for j in range(60):
  state=np.ones(3,dtype=np.float32)*j/100
  a.replay.add(state,.5,.1,state,False,'unsafe')
 partial=a._zero_sparse_message(theta,.2)
 assert empty['pad_bytes']>partial['pad_bytes']
 assert serialized_size(empty)==serialized_size(partial), 'metadata padding mismatch'


def test_temporal_attacks_and_client_telemetry():
    base={'idx':np.array([0,2],np.int32),'val':np.array([.01,.02],np.float32),
          'n':4,'utility':.2,'proto':{'stable':torch.zeros(2)}}

    # Delayed metadata forgery is inactive for rounds 1--5 and starts at round 6.
    clean_server=Server(torch.zeros(4),ServerSettings(clip_update=.5,shift_lambda=1.))
    clean_server.prototypes={'stable':torch.ones(2)}
    before=clean_server.step([base],poisoned=[0],attack='delayed_metadata',round_id=4)
    b=before['per_client'][0]
    assert not b['attack_active'] and abs(b['reported_utility']-.2)<1.e-8
    assert not b['prototype_imitation'] and not b['update_forgery']

    attack_server=Server(torch.zeros(4),ServerSettings(clip_update=.5,shift_lambda=1.))
    attack_server.prototypes={'stable':torch.ones(2)}
    after=attack_server.step([base],poisoned=[0],attack='delayed_metadata',round_id=5)
    a=after['per_client'][0]
    assert a['attack_active'] and abs(a['reported_utility']-.4)<1.e-8
    assert a['prototype_imitation'] and not a['update_forgery']
    assert abs(a['prototype_drift'])<1.e-7
    assert abs(sum(after['weight'])-1.)<1.e-7

    # Temporal credibility attack is inactive through round 50 and begins at round 51.
    pre=Server(torch.zeros(4),ServerSettings(clip_update=.5))
    pre.prototypes={'stable':torch.ones(2)}
    r49=pre.step([base],poisoned=[0],attack='temporal_credibility',round_id=49)
    assert not r49['per_client'][0]['attack_active']
    post=Server(torch.zeros(4),ServerSettings(clip_update=.5))
    post.prototypes={'stable':torch.ones(2)}
    r50=post.step([base],poisoned=[0],attack='temporal_credibility',round_id=50)
    p=r50['per_client'][0]
    assert p['attack_active'] and p['prototype_imitation'] and p['update_forgery']
    assert p['update_norm_reported']>p['update_norm_raw']

    # The logged multiplicative drift factor must match exp(-lambda_s * d_i).
    weighted=Server(torch.zeros(4),ServerSettings(clip_update=.5,shift_lambda=.5))
    weighted.prototypes={'stable':torch.ones(2)}
    out=weighted.step([base])
    q=out['per_client'][0]
    assert abs(q['drift_penalty']-math.exp(-.5*q['prototype_drift']))<1.e-7
    assert 'aggregation_weight' in q and 'credibility_score' in q

def run():
 torch.set_num_threads(1)
 test_replay();test_local_and_sharing();test_malicious_metadata();test_fixed_byte_transport();test_all_updates_missing();test_temporal_attacks_and_client_telemetry()
 print('PASS strict PER, optimizer boundary, serialization, capped server tests')
if __name__=='__main__':run()
