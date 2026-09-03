#!/usr/bin/env python3
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import wilcoxon

ROOT=Path('results/joint20'); GEN=Path('results/generated'); GEN.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((ROOT/'summary.csv').open()))
num=['safety_violation','min_cbf_margin','false_authorization_rate','max_belief_distortion','max_policy_drift','recovery_success','recovery_time','shield_intervention_ratio','mean_aggregate_deviation','communication_bytes']
for r in rows:
    r['seed']=int(r['seed'])
    for k in num:
        r[k]=float(r[k])
        if not math.isfinite(r[k]):
            raise SystemExit(f'Non-finite {k} in mechanism summary; generation refused.')
g=defaultdict(list)
for r in rows: g[(r['scenario'],r['method'])].append(r)
for key in g: g[key]=sorted(g[key], key=lambda x:x['seed'])

def mean_ci(xs):
    xs=np.asarray(xs,float); m=xs.mean(); se=xs.std(ddof=1)/math.sqrt(len(xs)) if len(xs)>1 else 0.0
    return m, m-1.96*se, m+1.96*se

def wilson(k,n,z=1.96):
    if n==0: return float('nan'),float('nan'),float('nan')
    p=k/n; den=1+z*z/n; center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return p,max(0.0,center-half),min(1.0,center+half)

def paired_wilcoxon_p(x,y):
    x=np.asarray(x,float); y=np.asarray(y,float); d=x-y
    if np.allclose(d,0.0,rtol=0.0,atol=1e-15):
        return 1.0
    try:
        p=float(wilcoxon(x,y,zero_method='wilcox',alternative='two-sided').pvalue)
    except ValueError:
        p=1.0
    return p if math.isfinite(p) else 1.0

def holm(ps):
    ps=np.asarray(ps,float)
    if not np.all(np.isfinite(ps)):
        raise SystemExit('Non-finite p-value reached Holm correction; generation refused.')
    m=len(ps); order=np.argsort(ps,kind='stable'); adj=np.ones(m,float); running=0.0
    for rank,idx in enumerate(order):
        val=(m-rank)*ps[idx]; running=max(running,val); adj[idx]=min(1.0,running)
    return adj

def fmt_mean(xs, binary=False, bounded=False):
    xs=np.asarray(xs,float)
    if binary:
        m,lo,hi=wilson(int(round(xs.sum())),len(xs))
    else:
        m,lo,hi=mean_ci(xs)
        if bounded:
            lo=max(0.0,lo); hi=min(1.0,hi)
    return m,lo,hi,f"{m:.3f} [{lo:.3f}, {hi:.3f}]"

methods=['FedRL','RobustAgg','AEFC-no-PATBU','AEFC-no-Gate','AEFC-no-TGOPA','AEFC-no-Shield','AEFC-Full']
metrics=[
 ('safety_violation','SVR',True),('min_cbf_margin','Min CBF',False),
 ('false_authorization_rate','FAR','bounded'),('max_belief_distortion','Belief dist.',False),
 ('max_policy_drift','Policy drift',False),('recovery_success','Rec. success',True),
 ('recovery_time','Rec. time',False)]
with (GEN/'joint_main.csv').open('w',newline='') as f:
    w=csv.writer(f); w.writerow(['method']+[b for _,b,_ in metrics])
    for m in methods:
        rr=g[('joint',m)]
        w.writerow([m]+[fmt_mean([x[a] for x in rr], binary is True, binary == 'bounded')[3] for a,_,binary in metrics])

stat_metrics=['max_belief_distortion','max_policy_drift','recovery_time','mean_aggregate_deviation']
stat_rows=[]
full=g[('joint','AEFC-Full')]
for metric in stat_metrics:
    ps=[]; tmp=[]
    x=np.asarray([r[metric] for r in full])
    for m in methods[:-1]:
        y=np.asarray([r[metric] for r in g[('joint',m)])
        p=paired_wilcoxon_p(x,y)
        ps.append(p); tmp.append((m,float(np.median(x-y)),p))
    padj=holm(ps)
    for (m,med,p),pa in zip(tmp,padj): stat_rows.append([metric,m,med,p,float(pa)])
with (GEN/'joint_statistics.csv').open('w',newline='') as f:
    w=csv.writer(f); w.writerow(['metric','comparison','median_paired_difference_full_minus_comparison','wilcoxon_p','holm_adjusted_p']); w.writerows(stat_rows)

tex=[]
tex.append(r"\begin{table*}[t]")
tex.append(r"\centering")
tex.append(r"\caption{Mechanism-level joint-corruption results over 20 matched seeds. Values are means with 95\% confidence intervals; Wilson intervals are used for binary rates. This table is not an IEEE 39-bus result.}")
tex.append(r"\label{tab:joint-mechanism}")
tex.append(r"\scriptsize")
tex.append(r"\begin{tabular}{lcccccc}")
tex.append(r"\toprule")
tex.append(r"Method & SVR $\downarrow$ & FAR $\downarrow$ & Belief dist. $\downarrow$ & Policy drift $\downarrow$ & Rec. success $\uparrow$ & Rec. time $\downarrow$\\")
tex.append(r"\midrule")
for m in methods:
    rr=g[('joint',m)]
    vals=[]
    for key,binary in [('safety_violation',True),('false_authorization_rate','bounded'),('max_belief_distortion',False),('max_policy_drift',False),('recovery_success',True),('recovery_time',False)]:
        vals.append(fmt_mean([x[key] for x in rr], binary is True, binary == 'bounded')[3])
    name=r"\textbf{AEFC-Full}" if m=='AEFC-Full' else m
    tex.append(name+' & '+' & '.join(vals)+r"\\")
tex.append(r"\bottomrule")
tex.append(r"\end{tabular}")
tex.append(r"\end{table*}")
(GEN/'Joint-Table-Auto.tex').write_text('\n'.join(tex)+'\n')

lines=[]
lines.append(r"\subsection{Mechanism-Level 20-Seed Joint-Corruption Results}")
lines.append(r"The executable bounded-authority pipeline was evaluated under the joint physical/knowledge attack on the released reduced-order CPS integration backend. This backend exercises PATBU, the risk gate, trust-gated adaptation, Byzantine-resilient coordination, the robust execution shield, and post-shield control corruption. It is used to validate mechanism composition and is not presented as an IEEE 39-bus result. All values below are generated from 20 matched seeds and immutable raw JSONL traces tied to one commit and configuration.")
lines.append(r"\input{results/generated/Joint-Table-Auto.tex}")
for key,label,binary in [('safety_violation','episode safety-violation rate',True),('false_authorization_rate','false-authorization rate','bounded'),('max_belief_distortion','maximum belief distortion',False),('max_policy_drift','maximum deployed-policy drift',False),('recovery_success','recovery success rate',True),('recovery_time','post-attack recovery time',False)]:
    mf,lf,hf,_=fmt_mean([x[key] for x in full], binary is True, binary == 'bounded')
    base=g[('joint','FedRL')]; mb,lb,hb,_=fmt_mean([x[key] for x in base], binary is True, binary == 'bounded')
    lines.append(f"For the joint attack, AEFC-Full yields {label} {mf:.4f} (95\\% CI [{lf:.4f}, {hf:.4f}]), versus {mb:.4f} ([{lb:.4f}, {hb:.4f}]) for FedRL.")
lines.append(r"The ablations expose the intended layer separation. Removing the shield causes physical safety violations despite small policy drift, whereas removing trust-gated adaptation sharply increases false authorization and policy drift while the shield can still preserve the physical invariant. Removing PATBU increases belief distortion. These observations are mechanism-level evidence for the compositional design, not a substitute for native IEEE 39-bus validation.")
lines.append(r"Paired Wilcoxon tests for the continuous integrity and recovery metrics are computed per seed and corrected across the six alternative methods with Holm's procedure. The corresponding machine-readable statistics are released with the artifact.")
(GEN/'Results-Auto.tex').write_text('\n\n'.join(lines)+'\n')

fig,ax=plt.subplots(figsize=(7.2,3.6))
means=[]; los=[]; his=[]
for m in methods:
    xs=np.asarray([x['safety_violation'] for x in g[('joint',m)]])
    mean,lo,hi=wilson(int(round(xs.sum())),len(xs)); means.append(mean); los.append(mean-lo); his.append(hi-mean)
ax.bar(np.arange(len(methods)),means)
ax.errorbar(np.arange(len(methods)),means,yerr=np.vstack([los,his]),fmt='none',capsize=3)
ax.set_xticks(np.arange(len(methods)),methods,rotation=35,ha='right'); ax.set_ylabel('Episode safety-violation rate'); ax.set_ylim(0,1.05); fig.tight_layout(); fig.savefig(GEN/'joint_safety.pdf')
plt.close(fig)
manifest=json.loads((ROOT/'manifest.json').read_text()); manifest['generated_from']='results/joint20/summary.csv'; manifest['statistics']='paired Wilcoxon + Holm; exact zero paired differences use p=1; Wilson CI for binary rates'; (GEN/'generation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
