"""Reanalyze the earlier audited five-method cohort without imputing new means."""
import argparse,csv,json
from pathlib import Path
import numpy as np
from audit_reviewer_r5 import describe,signflip,holm,csvout,TARGET,METRICS,need

def run(source,out):
    records={}
    with source.open(newline='') as f:
        for r in csv.DictReader(f):
            key=(int(r['seed']),r['mode']);need(key not in records,'duplicate')
            need(int(r['train_episodes'])==1000 and int(r['evaluation_episodes'])==10,'wrong budget')
            need(len(r['checkpoint_sha256'])==64 and len(r['source_json_sha256'])==64,'missing source hash')
            records[key]=r
    modes=('adv','ordinary','adv_no_cw','dense','dense_cw'); seeds=range(80,90)
    need(set(records)=={(s,m) for s in seeds for m in modes},'incomplete archival cohort')
    source_commits=sorted({r['git_commit'] for r in records.values()});need(len(source_commits)==1,'mixed commits')
    metrics=('mean_terminal_restored_pct','safe_dwell_success_fraction','mean_restricted_recovery_score','failed_or_censored_count')
    summary=[];paired=[];match=[]
    for m in modes:
        for i,(metric,col) in enumerate(zip(METRICS,metrics)):
            vals=np.array([float(records[s,m][col]) for s in seeds])*(100 if i==1 else 1)
            summary.append(dict(control=m,metric=metric,**describe(vals)))
            match.append(dict(control=m,metric=metric,archival_mean=float(vals.mean()),manuscript_point=TARGET[m][i],difference=float(vals.mean()-TARGET[m][i])))
            if m!='adv':
                base=np.array([float(records[s,'adv'][col]) for s in seeds])*(100 if i==1 else 1)
                a=base-vals;paired.append(dict(control=m,metric=metric,**describe(a),p_exact_signflip=signflip(a)))
    holm(paired);out.mkdir(parents=True,exist_ok=True)
    csvout(out/'summary.csv',summary);csvout(out/'paired_differences.csv',paired);csvout(out/'manuscript_reconciliation.csv',match)
    (out/'audit.json').write_text(json.dumps(dict(source=str(source),source_commits=source_commits,n_runs=50,seed_ids=list(seeds),matches_latest_manuscript=False,note='Previously hash-audited raw cohort; this analysis uses its archived seed CSV, not the latest manuscript values. MADDPG not present.'),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.source,a.out)
