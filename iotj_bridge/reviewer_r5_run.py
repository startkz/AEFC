"""Reviewer 1.3/1.5: new AC cohort, never the unavailable native Simulink runs."""
import argparse, copy, hashlib, json, os, sys
from pathlib import Path
import numpy as np
import torch
from torch import nn
import strict_run as strict
from strict_agent import Agent, Policy, CATEGORIES, mlp

BASE_GRID = strict.RecoveryGrid
BASE_AGENT = strict.Agent


class FourFactorGrid(BASE_GRID):
    """Four binary interventions: mask, delay, attack group, saturation."""
    def __init__(self, case, clients, seed, hetero, attack='physical', horizon=30):
        if not (hetero.startswith('r5_') and len(hetero)==7 and set(hetero[3:]) <= {'0','1'}):
            raise ValueError(hetero)
        self.factor = tuple(map(int, hetero[3:]))
        self.target = 0 if self.factor[2] else clients-1
        super().__init__(case, clients, seed, 'base', attack='physical', horizon=horizon)

    def observations(self):
        raw = [v.copy() for v in strict.Grid.observations(self)]
        # Bypass the parent's attack-specific observation wrapper; apply the
        # declared delay, target and mask in one explicit order.
        active = 5 <= self.step_idx < 16
        hist = getattr(self, '_delay_history', [])
        out = [v.copy() for v in raw]
        if self.factor[1] and len(hist)>=2:
            for i in range(1,len(out),2): out[i][1:4] = hist[-2][i][1:4]
        self._delay_history = (hist + [[v.copy() for v in raw]])[-4:]
        if active:
            out[self.target][1] += .12
            out[self.target][2] -= .09
        if self.factor[0]:
            for i in range(1,len(out),2): out[i][2] = 0.
        self.last_observation = [v.tolist() for v in out]
        self.last_raw = [v.tolist() for v in raw]
        return out

    def step(self, actions):
        raw = np.asarray(actions, dtype=float).copy()
        cmd = raw.copy()
        if self.factor[3]: cmd[1::2] = np.minimum(cmd[1::2], .6)
        # Parent implementation applies the physical attack to C4. For a
        # target switch, disable parent attack only during transition and apply
        # the same command corruption here. Observation path remains explicit.
        active = 5 <= self.step_idx < 16
        recorded_obs = copy.deepcopy(self.last_observation)
        recorded_raw = copy.deepcopy(self.last_raw)
        if active: cmd[self.target] = np.clip(cmd[self.target]-.25,0,1)
        old_attack = self.attack
        self.attack = 'clean'
        try:
            obs, reward, done, info = super().step(cmd)
        finally:
            self.attack = old_attack
        info.update({'factor_bits':list(self.factor), 'attack_target':self.target,
                     'attack_active':int(active), 'raw_command':raw.tolist(),
                     'executed_command':cmd.tolist(), 'controller_observation':recorded_obs,
                     'actuator_saturation':int(bool(self.factor[3] and np.any(raw[1::2]>.6))),
                     'raw_observation':recorded_raw})
        return obs,reward,done,info


class PaddedEncoder(nn.Module):
    def __init__(self, latent):
        super().__init__(); self.latent=latent
    def forward(self, x):
        return torch.nn.functional.pad(x,(0,self.latent-x.shape[-1]))


class FixedHead(nn.Module):
    def forward(self, x): return torch.sigmoid(x[..., :1])


def specialized_agent(control):
    class R5Agent(BASE_AGENT):
        def __init__(self, obs_dim, seed, **kwargs):
            super().__init__(obs_dim, seed, **kwargs)
            self.latent_size=kwargs.get('latent',32)
            if control=='no_adapter':
                self.actor.encoder=PaddedEncoder(self.latent_size)
                self.actor.head=FixedHead()
                self.target_actor=copy.deepcopy(self.actor)
                # No local trainable encoder/head remains. Empty optimizer state
                # is saved by this wrapper, not used for learning.
                self.adapter_opt=None
        def local_fit(self, steps, prototypes=None, **kwargs):
            if control=='no_adapter': kwargs['disable_adapter']=True
            if control=='no_prototype': kwargs['disable_proto']=True
            return super().local_fit(steps,prototypes,**kwargs)
        def prototypes(self,window=512):
            return {} if control=='no_prototype' else super().prototypes(window)
        def _set_fixed_padding(self,message):
            expected=sum(8+len(k.encode('utf8'))+4*self.latent_size for k in CATEGORIES)
            present=sum(8+len(k.encode('utf8'))+4*len(v) for k,v in message['proto'].items())
            message['pad_bytes']=max(0,expected-present)
    return R5Agent


def centralized(seed, episodes, eval_episodes):
    """New MADDPG-style centralized-training baseline, local actors at execution.

    Joint observations/actions enter every local-reward critic, not the actors.
    This is an AC reconstruction, not a reproduction of the original simulator.
    """
    torch.set_num_threads(1); torch.manual_seed(seed); np.random.seed(seed)
    env=BASE_GRID(39,5,seed,'dim',attack='clean')
    dims=[len(v) for v in env.reset()]; n=len(dims); total=sum(dims)
    actors=[]; targets=[]; critics=[]; target_critics=[]; opts=[]; qopts=[]; rngs=[]
    for i,dim in enumerate(dims):
        torch.manual_seed(seed*100+i)
        a=Policy(dim,32,128); q=mlp([total+n,128,128,1])
        actors.append(a);targets.append(copy.deepcopy(a));critics.append(q);target_critics.append(copy.deepcopy(q))
        opts.append(torch.optim.Adam(a.parameters(),lr=.001));qopts.append(torch.optim.Adam(q.parameters(),lr=.001))
        rngs.append(np.random.default_rng(seed*100+i+1907))
    class LocalActor:
        def __init__(self,i): self.i=i
        def act(self,o,explore=False,sigma=.15):
            with torch.no_grad(): a=float(actors[self.i](torch.tensor(np.asarray(o)[None,:],dtype=torch.float32))[0,0])
            return float(np.clip(a+(rngs[self.i].normal(0,sigma) if explore else 0),0,1))
    eval_agents=[LocalActor(i) for i in range(n)]
    rng=np.random.default_rng(seed+1001); replay=[]; ep_rows=[]
    def tensor(x):return torch.as_tensor(np.asarray(x),dtype=torch.float32)
    def polyak(a,b):
        with torch.no_grad():
            for x,y in zip(a.parameters(),b.parameters()): y.mul_(.995).add_(.005*x)
    def split(x):return list(torch.split(x,dims,dim=1))
    for ep in range(episodes):
        obs=env.reset(); done=False; trace=[]; dwell=0; first=-1
        while not done:
            acts=[a.act(o,True) for a,o in zip(eval_agents,obs)]
            nxt,rew,done,info=env.step(acts)
            replay.append((np.concatenate(obs),acts,rew,np.concatenate(nxt),float(done)))
            if len(replay)>100000: replay.pop(0)
            trace.append({'t':env.step_idx,**info})
            dwell=dwell+1 if info['safe'] and info['restored_pct']>=90 else 0
            if dwell>=5 and first<0:first=env.step_idx-4
            obs=nxt
        ep_rows.append({'episode':ep+1,'final_restored_pct':trace[-1]['restored_pct'],
                        'safe_dwell5':int(first>=0),'recovery_step':first,'censored':int(first<0),
                        'steps_executed':len(trace),'trace':trace})
        if (ep+1)%5==0 and len(replay)>=128:
            for _ in range(5):
                batch=[replay[i] for i in rng.integers(len(replay),size=256)]
                s,a,r,ns,d=map(tensor,zip(*batch)); d=d[:,None]
                with torch.no_grad(): na=torch.cat([q(x) for q,x in zip(targets,split(ns))],dim=1)
                for i in range(n):
                    with torch.no_grad(): y=r[:,i:i+1]+.99*(1-d)*target_critics[i](torch.cat([ns,na],1))
                    loss=(critics[i](torch.cat([s,a],1))-y).square().mean()
                    qopts[i].zero_grad(); loss.backward(); qopts[i].step()
                    for p in critics[i].parameters():p.requires_grad_(False)
                    pol=[a[:,j:j+1].detach() if j!=i else actors[i](split(s)[i]) for j in range(n)]
                    aloss=-critics[i](torch.cat([s,*pol],1)).mean()
                    opts[i].zero_grad();aloss.backward();opts[i].step()
                    for p in critics[i].parameters():p.requires_grad_(True)
                    polyak(actors[i],targets[i]);polyak(critics[i],target_critics[i])
    tests=[]
    for e in range(eval_episodes):
        test=BASE_GRID(39,5,100000+seed*100+e,'dim',attack='clean')
        tests.append(strict.run_episode(test,eval_agents,False,1000000+seed*100+e,trace=True))
    summary={'backend':'pandapower AC quasi-static','case':39,'seed':seed,'method':'maddpg_ac',
             'hetero':'dim','attack':'clean','clients':5,'train_episodes':episodes,
             'completed_rounds':episodes//5,'eval_episodes':eval_episodes,'steps_per_episode':30,
             'optimizer':'five joint-critic and full-actor updates per 5 episodes; uniform joint replay',
             'uplink_bytes':None,'centralized_joint_replay':True}
    return {'summary':summary,'rounds':[],'tests':tests,'train_episodes':ep_rows}, {'actors':[a.state_dict() for a in actors],'critics':[q.state_dict() for q in critics]}


def run(args):
    if args.study=='main' and args.control=='maddpg_ac':
        data, checkpoint=centralized(args.seed,args.episodes,args.eval_episodes)
    else:
        strict.RecoveryGrid=BASE_GRID if args.study=='main' else FourFactorGrid
        strict.Agent=BASE_AGENT if args.study=='main' else specialized_agent(args.control)
        hetero='dim' if args.study=='main' else args.factor
        mode=args.control if args.study=='main' else ('dense' if args.control=='dense' else 'adv')
        # No fixed padding for the historical main protocol; matched sparse
        # message lengths across all three factor-study ablations.
        s,r,t,e,agents,server=strict.run(39,args.seed,mode,hetero,'clean' if args.study=='main' else 'physical',
            args.episodes,5,256,128,32,5,2,.2,args.eval_episodes,
            disable_proto=(args.control=='no_prototype'),malicious_clients=0,
            disable_adapters=(args.control=='no_adapter'),fixed_traffic=(args.study=='hetero'),record_training_trace=True)
        data={'summary':s,'rounds':r,'tests':t,'train_episodes':e}
        checkpoint={'actors':[a.actor.state_dict() for a in agents], 'critics':[a.critic.state_dict() for a in agents], 'server_theta':server.theta,'server_prototypes':server.prototypes}
    data['summary'].update({'r5_study':args.study,'r5_control':args.control,'r5_factor':args.factor if args.study=='hetero' else 'dim'})
    if args.study=='hetero':
        data['summary']['prototype_exchange_disabled']=int(args.control=='no_prototype')
        data['summary']['final_server_prototype_categories']=sorted(checkpoint['server_prototypes'])
    p=args.out;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,separators=(',',':'),allow_nan=False)+'\n')
    ck=p.with_suffix('.pt');torch.save(checkpoint,ck)
    m={'git_commit':os.environ.get('GITHUB_SHA','local'),'github_run_id':os.environ.get('GITHUB_RUN_ID','local'),
       'source_json_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'checkpoint_sha256':hashlib.sha256(ck.read_bytes()).hexdigest(),
       'training_episodes_executed':len(data['train_episodes']),'torch':torch.__version__,'python':sys.version.split()[0]}
    p.with_suffix('.manifest.json').write_text(json.dumps(m,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',choices=['main','hetero'],required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--control',required=True)
    p.add_argument('--factor',default='r5_0000');p.add_argument('--episodes',type=int,default=1000)
    p.add_argument('--eval-episodes',type=int,default=10);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    allowed=('adv','ordinary','adv_no_cw','dense','dense_cw','maddpg_ac') if a.study=='main' else ('adv','no_adapter','no_prototype','dense')
    if a.control not in allowed:p.error('invalid control for this study')
    run(a)
