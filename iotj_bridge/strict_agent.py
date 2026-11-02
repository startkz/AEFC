"""AEFC-FRL manuscript-aligned learner, implementation candidate.

This is deliberately separate from legacy aefc/PATBU and the earlier bridge
development prototype. See STRICT_REPRODUCTION.md for unverified assumptions.
"""
from __future__ import annotations
import copy, math, io, struct
from dataclasses import dataclass
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

CATEGORIES=("unsafe","recovering","stable")

def mlp(sizes,final=None):
    layers=[]
    for j in range(len(sizes)-1):
        layers.append(nn.Linear(sizes[j],sizes[j+1]))
        if j<len(sizes)-2:layers.append(nn.ReLU())
        elif final is not None:layers.append(final())
    return nn.Sequential(*layers)

def flatten(net):
    return torch.cat([p.detach().reshape(-1).cpu() for p in net.parameters()])

def set_flat(net,vector):
    z=torch.as_tensor(vector,dtype=torch.float32);pos=0
    with torch.no_grad():
        for p in net.parameters():
            count=p.numel();p.copy_(z[pos:pos+count].reshape_as(p));pos+=count
    if pos!=z.numel():raise ValueError("Incompatible backbone dimensions")

def norm_clip(v,limit):
    n=torch.linalg.vector_norm(v)
    return v*(min(1.,float(limit)/(float(n)+1.e-12)))

class PER:
    def __init__(self,obs_dim,capacity=100000,alpha=.6,beta0=.4,seed=0):
        self.capacity=int(capacity);self.alpha=float(alpha);self.beta0=float(beta0)
        self.obs=np.zeros((capacity,obs_dim),np.float32);self.next=np.zeros_like(self.obs)
        self.act=np.zeros((capacity,1),np.float32)
        self.rew=np.zeros((capacity,1),np.float32);self.done=np.zeros((capacity,1),np.float32)
        self.category=np.zeros(capacity,dtype=np.int8)
        self.prior=np.zeros(capacity,dtype=np.float64)
        self.n=0;self.pos=0;self.rng=np.random.default_rng(seed)
    def __len__(self):return self.n
    def add(self,obs,act,reward,nxt,done,category):
        j=self.pos
        self.obs[j]=obs;self.act[j,0]=act;self.rew[j,0]=reward
        self.next[j]=nxt;self.done[j,0]=float(done)
        self.category[j]=CATEGORIES.index(category)
        self.prior[j]=max(1.,float(self.prior[:self.n].max()) if self.n else 1.)
        self.pos=(j+1)%self.capacity;self.n=min(self.n+1,self.capacity)
    def sample(self,batch=256,beta=None):
        if not self.n:raise ValueError("empty replay")
        beta=self.beta0 if beta is None else float(beta)
        prob=np.maximum(self.prior[:self.n],1.e-10)**self.alpha
        prob=prob/prob.sum()
        indices=self.rng.choice(self.n,size=batch,replace=True,p=prob)
        weight=(self.n*prob[indices])**(-beta);weight=weight/weight.max()
        T=lambda arr:torch.from_numpy(arr[indices].copy())
        return {'s':T(self.obs),'a':T(self.act),'r':T(self.rew),
                'ns':T(self.next),'done':T(self.done),
                'category':torch.from_numpy(self.category[indices].copy()),
                'idx':indices,'isw':torch.tensor(weight,dtype=torch.float32).view(-1,1)}
    def update(self,indices,td_error,eps=1.e-6):
        p=np.abs(np.asarray(td_error,dtype=float).ravel())+eps
        for i,val in zip(indices,p):
            self.prior[int(i)]=max(self.prior[int(i)],float(val)) if False else float(val)

class Policy(nn.Module):
    def __init__(self,obs_dim,latent=32,hidden=128,act_low=0.,act_high=1.):
        super().__init__()
        self.encoder=mlp([obs_dim,hidden,latent])
        self.backbone=mlp([latent,hidden,hidden,latent])
        self.head=mlp([latent,hidden,1],nn.Sigmoid)
        self.register_buffer("lo",torch.tensor(float(act_low)))
        self.register_buffer("hi",torch.tensor(float(act_high)))
    def forward(self,obs):
        value=self.head(self.backbone(self.encoder(obs)))
        return self.lo+(self.hi-self.lo)*value

class Agent:
    def __init__(self,obs_dim,seed,latent=32,hidden=128,act_low=0.,act_high=1.,
                 actor_lr=.001,critic_lr=.001,gamma=.99,tau=.005,
                 capacity=100000,per_alpha=.6,per_beta=.4,batch=256,align_lambda=.01):
        torch.manual_seed(int(seed))
        self.actor=Policy(obs_dim,latent,hidden,act_low,act_high)
        self.target_actor=copy.deepcopy(self.actor)
        self.critic=mlp([obs_dim+1,hidden,hidden,1])
        self.target_critic=copy.deepcopy(self.critic)
        self.replay=PER(obs_dim,capacity,per_alpha,per_beta,seed)
        self.critic_opt=torch.optim.Adam(self.critic.parameters(),lr=critic_lr)
        self.adapter_opt=torch.optim.Adam(list(self.actor.encoder.parameters())+
                                          list(self.actor.head.parameters()),lr=actor_lr)
        self.gamma=float(gamma);self.tau=float(tau)
        self.batch=int(batch);self.actor_lr=float(actor_lr)
        self.align_lambda=float(align_lambda)
        self.rng=np.random.default_rng(seed+1907)
        self.last_adapt={}
    def set_global(self,theta):
        set_flat(self.actor.backbone,theta)
        # The target tracks global steps through Polyak at each synchronization.
        self.polyak(self.actor.backbone,self.target_actor.backbone)
    def act(self,obs,explore=False,sigma=.15):
        with torch.no_grad():
            action=float(self.actor(torch.tensor(np.asarray(obs)[None,:],dtype=torch.float32))[0,0])
        if explore:action+=self.rng.normal(0,sigma)
        return float(np.clip(action,float(self.actor.lo),float(self.actor.hi)))
    def polyak(self,source,target):
        with torch.no_grad():
            for a,b in zip(source.parameters(),target.parameters()):
                b.mul_(1-self.tau).add_(self.tau*a)
    def local_fit(self,steps,prototypes=None,disable_proto=False,update_after=256,disable_adapter=False):
        if len(self.replay)<update_after:return {'updates':0}
        for p in self.actor.backbone.parameters():p.requires_grad_(False)
        n=0;last_td=0.;last_align=0.
        for _ in range(int(steps)):
            b=self.replay.sample(self.batch)
            s,a,r,ns,d=b['s'],b['a'],b['r'],b['ns'],b['done']
            with torch.no_grad():
                target=r+self.gamma*(1-d)*self.target_critic(torch.cat([ns,self.target_actor(ns)],dim=1))
            q=self.critic(torch.cat([s,a],dim=1))
            td=q-target
            critic_loss=(b['isw']*td.square()).mean()
            self.critic_opt.zero_grad(set_to_none=True)
            critic_loss.backward();self.critic_opt.step()
            self.replay.update(b['idx'],td.detach().numpy())
            if disable_adapter:
                # Controlled no-local-adapter comparator; only critic learns.
                # Shared backbone remains unchanged during this local phase.
                self.polyak(self.critic,self.target_critic)
                n+=1;last_td=float(td.square().mean());last_align=0.
                continue
            # Critic is fixed for the adapter step, while the actor action remains differentiable.
            for p in self.critic.parameters():p.requires_grad_(False)
            act=self.actor(s)
            actor_loss=-(b['isw']*self.critic(torch.cat([s,act],dim=1))).mean()
            penalty=torch.tensor(0.)
            if prototypes and not disable_proto:
                enc=self.actor.encoder(s)
                for m,globalp in prototypes.items():
                    cidx=CATEGORIES.index(m)
                    sel=b['category']==cidx
                    if bool(sel.any()):
                        # Equation L_align: mean squared distance of every local feature.
                        penalty=penalty+((enc[sel]-globalp[None,:])**2).sum(-1).mean()
                actor_loss=actor_loss+self.align_lambda*penalty
            self.adapter_opt.zero_grad(set_to_none=True)
            actor_loss.backward();self.adapter_opt.step()
            for p in self.critic.parameters():p.requires_grad_(True)
            self.polyak(self.actor.encoder,self.target_actor.encoder)
            self.polyak(self.actor.head,self.target_actor.head)
            self.polyak(self.critic,self.target_critic)
            n+=1;last_td=float(td.square().mean());last_align=float(penalty)
        for p in self.actor.backbone.parameters():p.requires_grad_(True)
        self.last_adapt={'updates':n,'td_mse':last_td,'align_loss':last_align}
        return self.last_adapt
    def prototypes(self,window=512):
        if not len(self.replay):return {}
        # Chronological newest-first circular indices, not replay priority duplicates.
        index=(np.arange(min(window,len(self.replay)))+self.replay.pos-min(window,len(self.replay)))%self.replay.capacity
        x=torch.tensor(self.replay.obs[index],dtype=torch.float32)
        categories=self.replay.category[index]
        with torch.no_grad():z=self.actor.encoder(x)
        return {m:z[categories==i].mean(0).cpu() for i,m in enumerate(CATEGORIES)
                if np.any(categories==i)}
    def share(self,theta,mode="adv",kappa=.2,sharing_steps=2,zeta=0.,
              fixed_batch=None):
        set_flat(self.actor.backbone,theta)
        if len(self.replay)<1:return None
        b=self.replay.sample(self.batch) if fixed_batch is None else fixed_batch
        s,a=b['s'],b['a']
        with torch.no_grad():
            qbeh=self.critic(torch.cat([s,a],dim=1))
            qpol=self.critic(torch.cat([s,self.actor(s)],dim=1))
            advantage=(qbeh-qpol).flatten()
            isw=b['isw'].flatten()
            selected=torch.nonzero(advantage>zeta).flatten()
            n=int(selected.numel())
            # Non-adv selection methods have matched transition counts, independent of advantages.
            if mode in ('dense','critic_share'):selected=torch.arange(len(s))
            elif mode=="ordinary":selected=torch.arange(len(s))[:n]
            elif mode=="random":
                selected=torch.randperm(len(s),generator=torch.Generator().manual_seed(int(self.rng.integers(2**31))))[:n]
            elif mode=="td":
                ns,r,d=b['ns'],b['r'],b['done']
                y=r+self.gamma*(1-d)*self.target_critic(torch.cat([ns,self.target_actor(ns)],dim=1))
                td=(y-qbeh).abs().flatten()
                selected=torch.argsort(td,descending=True,stable=True)[:n]
            elif mode not in ("adv","uniform_high"):raise ValueError(mode)
        if not len(selected):return None
        # v_j*A_j normalized for advantage; compare high-set uniform and ordinary.
        if mode=="adv":raw=(isw[selected]*advantage[selected]).detach().clamp_min(0)
        else:raw=isw[selected].detach().clamp_min(0)
        if float(raw.sum())<=0:return None
        weight=(raw/raw.sum()).detach()
        for p in list(self.actor.encoder.parameters())+list(self.actor.head.parameters())+list(self.critic.parameters()):
            p.requires_grad_(False)
        opt=torch.optim.Adam(self.actor.backbone.parameters(),lr=self.actor_lr)
        # Detached reference actions and selected batch are held fixed during sharing.
        for _ in range(int(sharing_steps)):
            q=self.critic(torch.cat([s[selected],self.actor(s[selected])],dim=1)).flatten()
            loss=-(weight*q).sum()
            opt.zero_grad(set_to_none=True);loss.backward();opt.step()
        delta=flatten(self.actor.backbone)-torch.as_tensor(theta)
        k=max(1,int(math.ceil((1.0 if mode in ('dense','critic_share') else float(kappa))*delta.numel())))
        # Stable magnitude sort: smaller coordinate wins ties.
        indices=torch.argsort(delta.abs(),descending=True,stable=True)[:k].sort().values
        message={'idx':indices.numpy().astype(np.int32),
                 'val':delta[indices].numpy().astype(np.float32),
                 'n':int(delta.numel()),'utility':float(advantage[selected].mean()),
                 'proto':self.prototypes(),
                 'high_count':int(n),'selection_count':int(len(selected)),
                 'uncompressed':delta.numpy().copy()}
        for p in list(self.actor.encoder.parameters())+list(self.actor.head.parameters())+list(self.critic.parameters()):
            p.requires_grad_(True)
        set_flat(self.actor.backbone,theta)
        return message

def serialized_size(m):
    if m is None:return 0
    f=io.BytesIO()
    f.write(struct.pack('<IIf',int(m['n']),len(m['idx']),float(m['utility'])))
    f.write(np.asarray(m['idx'],dtype='<i4').tobytes())
    f.write(np.asarray(m['val'],dtype='<f4').tobytes())
    f.write(struct.pack('<I',len(m['proto'])))
    for name,vec in sorted(m['proto'].items()):
        key=name.encode('utf8');v=np.asarray(vec,dtype='<f4')
        f.write(struct.pack('<II',len(key),len(v)));f.write(key);f.write(v.tobytes())
    return len(f.getvalue())

@dataclass
class ServerSettings:
    clip_update:float=.075
    clip_proto:float=2.
    cap_utility:float=1.
    epsilon:float=.001
    epsilon_proto:float=1.e-9
    shift_lambda:float=1.
    eta_global:float=1.
    max_weight:float|None=None
    equal_weight:bool=False

class Server:
    def __init__(self,theta,settings=None):
        self.theta=torch.as_tensor(theta,dtype=torch.float32).clone()
        self.prototypes={}
        self.settings=settings or ServerSettings()
    def step(self,messages,poisoned=None,attack=None,round_id=0):
        config=self.settings;weighted=[];scores=[];payload=[]
        seen=set();traffic=0
        for pos,original in enumerate(messages):
            if original is None:continue
            m={**original,'idx':np.asarray(original['idx']).copy(),
               'val':np.asarray(original['val'],dtype=np.float32).copy(),
               'proto':{k:torch.as_tensor(v).clone() for k,v in original['proto'].items()}}
            if pos in (poisoned or ()) and attack:
                if attack in ('joint','utility','delayed_joint'):
                    if attack!='delayed_joint' or round_id>=5:m['utility']=config.cap_utility
                if attack in ('joint','proto','delayed_joint') and self.prototypes:
                    if attack!='delayed_joint' or round_id>=5:m['proto']={k:v.clone() for k,v in self.prototypes.items()}
                if attack in ('joint','update','delayed_joint') and (attack!='delayed_joint' or round_id>=5):
                    m['val']=np.asarray(-np.sign(m['val']+1.e-12)*(np.abs(m['val'])*2+.01),dtype=np.float32)
            traffic+=serialized_size(m)
            idx=np.asarray(m['idx'],dtype=np.int64)
            val=np.asarray(m['val'],dtype=np.float32)
            if (len(idx)!=len(val) or np.any(idx<0) or np.any(idx>=len(self.theta))
                or len(set(idx.tolist()))!=len(idx) or m['n']!=len(self.theta)
                or not np.isfinite(val).all() or not np.isfinite(float(m['utility']))
                or any(k not in CATEGORIES or not torch.isfinite(p).all() or p.ndim!=1
                       for k,p in m['proto'].items())):continue
            u=torch.zeros_like(self.theta);u[torch.from_numpy(idx)]=torch.from_numpy(val)
            u=norm_clip(u,config.clip_update)
            pr={k:norm_clip(x.float(),config.clip_proto) for k,x in m['proto'].items()}
            common=set(pr).intersection(self.prototypes)
            drift=float(np.mean([1-F.cosine_similarity(pr[k][None,:],
                                            self.prototypes[k][None,:],dim=1,eps=config.epsilon_proto).item()
                                 for k in common])) if common else 0.
            score=min(config.cap_utility,max(float(m['utility']),0))/(float(u.norm())+config.epsilon)*math.exp(-config.shift_lambda*drift)
            weighted.append((pos,u,pr));scores.append(score)
        if not weighted:
            return {'weight':np.zeros(len(messages)), 'upload_bytes':traffic,'accepted':0,'drift':[]}
        w=np.asarray(scores,dtype=float)
        w=w/w.sum() if w.sum()>0 else np.ones_like(w)/len(w)
        if config.equal_weight:w=np.ones_like(w)/len(w)
        if config.max_weight is not None:
            cap=float(config.max_weight)
            if cap<len(w)**-1 or cap>1:raise ValueError("infeasible weight cap")
            fixed=np.zeros(len(w));remain=1.;free=list(range(len(w)))
            while free:
                s=float(w[free].sum())
                overflow=[j for j in free if s>0 and w[j]/s*remain>cap+1.e-12]
                if not overflow:
                    for j in free:fixed[j]=remain*w[j]/s if s else remain/len(free)
                    break
                for j in overflow:fixed[j]=cap;remain-=cap;free.remove(j)
            w=fixed
        direction=torch.zeros_like(self.theta);fullweights=np.zeros(len(messages))
        for weight,(pos,u,p) in zip(w,weighted):
            direction+=float(weight)*u;fullweights[pos]=weight
        self.theta=self.theta+config.eta_global*direction
        for name in CATEGORIES:
            eligible=[(float(wgt),p[name]) for wgt,(_,_,p) in zip(w,weighted) if name in p]
            s=sum(weight for weight,_ in eligible)
            if s>0:self.prototypes[name]=sum(weight*p for weight,p in eligible)/s
        return {'weight':fullweights,'upload_bytes':traffic,'accepted':len(weighted),
                'direction':direction,'malicious_weight':sum(fullweights[j] for j in (poisoned or ()))}
