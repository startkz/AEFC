#!/usr/bin/env python3
"""White-box membership inference on a trained local AEFC-FRL adapter.

A strong local-model-exposure attack, NOT a server-only attack: the attacker
knows local actor/encoder and critic, which are not normally federated.
Positive candidate observations come from the client's actual PER buffer;
negative candidates come from disjoint-seed held-out rollouts. Shadow clients
are disjoint from the target client, but temporal state-distribution changes
can confound membership and must be acknowledged in the paper.
"""
import argparse,csv,json,os
from pathlib import Path
import numpy as np
import torch
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
try:
 from .strict_run import run, RecoveryGrid
except ImportError:
 from strict_run import run, RecoveryGrid

def nonmember_states(case,seed,agents,clients=5,episodes=8):
    collected=[[] for _ in range(clients)]
    for k in range(episodes):
        env=RecoveryGrid(case,clients,seed*10000+5000+k,'dim',attack='clean')
        obs=env.reset();done=False
        while not done:
            for j,x in enumerate(obs):collected[j].append(x.copy())
            actions=[a.act(x,explore=True) for a,x in zip(agents,obs)]
            obs,_,done,_=env.step(actions)
    return [np.stack(x) for x in collected]

def features(agent,x):
    with torch.no_grad():
        s=torch.tensor(x,dtype=torch.float32)
        action=agent.actor(s)
        z=agent.actor.encoder(s)
        value=agent.critic(torch.cat([s,action],1)).flatten()
        proto=agent.prototypes()
        distances=[]
        for key in ('unsafe','recovering','stable'):
            if key in proto:
                distances.append(torch.linalg.vector_norm(z-proto[key][None,:],dim=1))
            else:
                distances.append(torch.full((len(s),),3.,dtype=torch.float32))
        return np.stack([value.numpy(),action.flatten().numpy(),z.norm(dim=1).numpy(),
                         *[d.numpy() for d in distances]],axis=1)

def perform(case,train_seed,episodes=1000,attacks=(500,501,502),candidate_count=128):
    torch.set_num_threads(1)
    _,_,_,_,agents,_=run(case=case,seed=train_seed,mode='adv',hetero='dim',
        attack='clean',episodes=episodes,clients_n=5,batch=256,
        hidden=128,latent=32,steps=5,sharing_steps=2,kappa=.2,
        eval_episodes=3,fixed_traffic=True)
    negatives=nonmember_states(case,train_seed,agents)
    all_rows=[];summaries=[]
    for attack_seed in attacks:
        g=np.random.default_rng(train_seed*10000+attack_seed)
        dataset=[]
        for client_id,a in enumerate(agents):
            eligible=a.replay.obs[:len(a.replay)]
            neg=negatives[client_id]
            n=min(candidate_count,len(eligible),len(neg))
            members=eligible[g.choice(len(eligible),n,replace=False)]
            nonmembers=neg[g.choice(len(neg),n,replace=False)]
            xb=np.concatenate([members,nonmembers])
            label=np.r_[np.ones(n,dtype=int),np.zeros(n,dtype=int)]
            feat=features(a,xb)
            dataset.append((feat,label,n,client_id))
        # train shadow attack on same-observation-dimension clients 0 and 2,
        # evaluate on a disjoint target client 4.
        X=np.concatenate([dataset[0][0],dataset[2][0]])
        Y=np.concatenate([dataset[0][1],dataset[2][1]])
        target=dataset[4]
        attack=make_pipeline(StandardScaler(),LogisticRegression(C=1.,max_iter=1000))
        attack.fit(X,Y)
        prob=attack.predict_proba(target[0])[:,1]
        auc=float(roc_auc_score(target[1],prob))
        summaries.append({'grid':case,'train_seed':train_seed,'attack_seed':attack_seed,
            'target_client':4,'n_members':target[2],'n_nonmembers':target[2],
            'shadow_clients':[0,2],'auc':auc,
            'attacker_view':'white-box local encoder, actor, critic and prototypes'})
        for i,(truth,score) in enumerate(zip(target[1],prob)):
            all_rows.append({'grid':case,'train_seed':train_seed,'attack_seed':attack_seed,
              'target_client':4,'candidate_id':i,'member_label':int(truth),
              'prediction_score':float(score)})
    return summaries,all_rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--case',type=int,choices=[39,118],required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--episodes',type=int,default=1000)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    summaries,rows=perform(args.case,args.seed,args.episodes)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'summary':summaries,
       'protocol':{'positive':'record from retained PER buffer',
          'negative':'disjoint-seed simulator rollout from final policy',
          'shadow_clients':[0,2],'target_client':4,
          'claim_scope':'strong white-box adapter/critic-access; NOT a server-only attack',
          'limitation':'candidate distribution may shift across training and evaluation',
          'git_sha':os.environ.get('GITHUB_SHA','unknown')}},indent=2)+'\n')
    out=args.out.with_suffix('.predictions.csv')
    with out.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'case':args.case,'train_seed':args.seed,
           'attack_seeds':len(summaries),'auc':[x['auc'] for x in summaries],
           'saved_prediction_rows':len(rows)}))
if __name__=='__main__':main()
