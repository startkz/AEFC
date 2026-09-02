#!/usr/bin/env python3
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT=Path('results/joint20'); GEN=Path('results/generated'); GEN.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((ROOT/'summary.csv').open()))
num=['safety_violation','min_cbf_margin','false_authorization_rate','max_belief_distortion','max_policy_drift','recovery_success','recovery_time','shield_intervention_ratio','mean_aggregate_deviation','communication_bytes']
for r in rows:
    for k in num: r[k]=float(r[k])
g=defaultdict(list)
for r in rows: g[(r['scenario'],r['method'])].append(r)

def ci95(xs):
    xs=np.asarray(xs,float); m=xs.mean(); se=xs.std(ddof=1)/math.sqrt(len(xs)) if len(xs)>1 else 0
    return m,1.96*se

methods=['FedRL','RobustAgg','AEFC-no-PATBU','AEFC-no-Gate','AEFC-no-TGOPA','AEFC-no-Shield','AEFC-Full']
metrics=[('safety_violation','SVR'),('min_cbf_margin','Min CBF'),('false_authorization_rate','FAR'),('max_belief_distortion','Belief dist.'),('max_policy_drift','Policy drift'),('recovery_success','Rec. success'),('recovery_time','Rec. time')]
with (GEN/'joint_main.csv').open('w',newline='') as f:
    w=csv.writer(f); w.writerow(['method']+[b for _,b in metrics])
    for m in methods:
        rr=g[('joint',m)]; w.writerow([m]+[ci95([x[a] for x in rr])[0] for a,_ in metrics])

lines=[]
lines.append(r"\subsection{Mechanism-Level 20-Seed Joint-Corruption Results}")
lines.append(r"The executable security pipeline was first validated on the released reduced-order CPS backend. This backend exercises the complete PATBU--gate--adaptation--shield path and the post-shield attack ordering, but it is not reported as an IEEE 39-bus result. Each entry below is computed from 20 matched seeds and immutable raw JSONL traces produced by the same commit and configuration.")
full=g[('joint','AEFC-Full')]; base=g[('joint','FedRL')]
for key,label in [('safety_violation','episode safety-violation rate'),('false_authorization_rate','false-authorization rate'),('max_belief_distortion','maximum belief distortion'),('max_policy_drift','maximum deployed-policy drift'),('recovery_success','recovery success rate'),('recovery_time','post-attack recovery time')]:
    mf,hf=ci95([x[key] for x in full]); mb,hb=ci95([x[key] for x in base])
    lines.append(f"For the joint physical/knowledge attack, AEFC-Full obtains {label} {mf:.4f} $\\pm$ {hf:.4f} (95\\% normal-approximation CI half-width), compared with {mb:.4f} $\\pm$ {hb:.4f} for FedRL.")
lines.append(r"These measurements validate executable mechanism composition only. IEEE 39-bus claims remain pending until the licensed R2024b workflow produces native-model traces.")
(GEN/'Results-Auto.tex').write_text('\n\n'.join(lines)+'\n')

fig,ax=plt.subplots(figsize=(7.2,3.6))
means=[np.mean([x['safety_violation'] for x in g[('joint',m)]]) for m in methods]
ax.bar(np.arange(len(methods)),means)
ax.set_xticks(np.arange(len(methods)),methods,rotation=35,ha='right'); ax.set_ylabel('Episode safety-violation rate'); ax.set_ylim(0,1.05); fig.tight_layout(); fig.savefig(GEN/'joint_safety.pdf')
plt.close(fig)
manifest=json.loads((ROOT/'manifest.json').read_text()); manifest['generated_from']='results/joint20/summary.csv'; (GEN/'generation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
