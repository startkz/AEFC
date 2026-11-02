#!/usr/bin/env python3
"""Semantic recovery-category alignment diagnostics with actual local adapters.

Only empirical alignment of three local recovery-state categories is assessed.
Category labels are weak operational indicators, not a semantic ground truth
for all cyber-physical subsystems.
"""
import argparse,json
from pathlib import Path
import numpy as np
import torch
try:
 from .strict_run import run
except ImportError:
 from strict_run import run

def study(case,seed,disable_proto=False,episodes=1000):
 result,rounds,tests,train,agents,server=run(
   case=case,seed=seed,mode='adv',hetero='dim',attack='clean',episodes=episodes,
   clients_n=5,batch=256,hidden=128,latent=32,steps=5,sharing_steps=2,
   kappa=.2,eval_episodes=10,disable_proto=disable_proto,fixed_traffic=True)
 per_client=[];dists=[];cosines=[]
 for i,client in enumerate(agents):
    local=client.prototypes()
    counts={cat:int((client.replay.category[:len(client.replay)]==j).sum())
            for j,cat in enumerate(('unsafe','recovering','stable'))}
    for category,ref in server.prototypes.items():
        if category not in local:continue
        observed=local[category]
        err=float(torch.linalg.vector_norm(ref-observed))
        cos=float(torch.nn.functional.cosine_similarity(ref[None,:],observed[None,:]).item())
        dists.append(err);cosines.append(cos)
        per_client.append({'client':i,'category':category,
            'support':counts[category],'distance_l2':err,'cosine':cos})
 within=float(np.mean(dists)) if dists else None
 between=[]
 keys=list(server.prototypes)
 for i in range(len(keys)):
    for j in range(i+1,len(keys)):
        between.append(float(torch.linalg.vector_norm(server.prototypes[keys[i]]-server.prototypes[keys[j]])))
 return {'grid':case,'seed':seed,'method':'adv','disable_proto':int(disable_proto),
   'episodes':episodes,'completed_rounds':result['completed_rounds'],
   'mean_heldout_load':result['mean_test_load_pct'],
   'safe_dwell_successes':result['safe_dwell_successes'],
   'avg_local_global_l2':within,
   'avg_local_global_cosine':float(np.mean(cosines)) if cosines else None,
   'global_interclass_min_l2':min(between) if between else None,
   'available_classes':keys,'client_class_metrics':per_client,
   'limitation':'weak recovery-state labels; local/global prototype alignment, not proven semantic equivalence'}
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--case',type=int,choices=[39,118],required=True)
 p.add_argument('--seed',type=int,required=True)
 p.add_argument('--episodes',type=int,default=1000)
 p.add_argument('--disable-proto',action='store_true')
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();torch.set_num_threads(1)
 r=study(a.case,a.seed,a.disable_proto,a.episodes)
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:v for k,v in r.items() if k!='client_class_metrics'}))
if __name__=='__main__':main()
