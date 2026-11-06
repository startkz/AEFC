#!/usr/bin/env python3
"""Independent audit of all previously archived prototype-on/off results.

Reads GitHub artifact JSON only: never retrains and never changes any reported
restoration percentage. Applies floating-point tolerance to 100% ceiling.
"""
import argparse,json,csv,math
from pathlib import Path
from collections import defaultdict

def audit(root,out):
    files=sorted(root.rglob('prototype_*.json'))
    rows=[];ids=set();errors=[]
    for path in files:
        try:
            x=json.loads(path.read_text())
            key=(int(x['grid']),int(x['seed']),int(x['disable_proto']))
            if key in ids:raise ValueError('duplicate')
            ids.add(key)
            if x['episodes']!=1000 or x['completed_rounds']!=200:
                raise ValueError('incomplete full budget')
            if not (-1.e-8<=x['mean_heldout_load']<=100+1.e-8):
                raise ValueError('restored load exceeds floating point tolerance')
            if x['safe_dwell_successes']<0 or x['safe_dwell_successes']>10:
                raise ValueError('invalid safe count')
            for z in x['client_class_metrics']:
                if z['support']<0 or not math.isfinite(z['distance_l2']) or not math.isfinite(z['cosine']):
                    raise ValueError('bad semantic per-class measurement')
            rows.append({'case':key[0],'seed':key[1],'disable_proto':key[2],
                         'load':x['mean_heldout_load'],'safe':x['safe_dwell_successes'],
                         'local_global_l2':x['avg_local_global_l2'],
                         'local_global_cosine':x['avg_local_global_cosine'],
                         'categories_present':','.join(x['available_classes']),
                         'n_class_observations':len(x['client_class_metrics'])})
        except Exception as ex:errors.append({'path':str(path),'reason':str(ex)})
    n={i:sum(1 for x in rows if x['case']==i) for i in (39,118)}
    pairs={}
    for c in (39,118):
        on={x['seed']:x for x in rows if x['case']==c and not x['disable_proto']}
        off={x['seed']:x for x in rows if x['case']==c and x['disable_proto']}
        common=sorted(set(on)&set(off))
        pairs[c]=[{'seed':s,'load_delta_on_minus_off':on[s]['load']-off[s]['load'],
                  'l2_delta_on_minus_off':on[s]['local_global_l2']-off[s]['local_global_l2'],
                  'safe_delta':on[s]['safe']-off[s]['safe']} for s in common]
        if len(common)!=3:errors.append({'case':c,'reason':'missing paired seeds'})
    out.mkdir(parents=True,exist_ok=True)
    if rows:
        with (out/'semantic_12_runs.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    report={'source':'original archived 12 jobs from run 41408245276',
            'original_results_modified':False,'input_json_count':len(files),
            'audited_rows':len(rows),'paired':pairs,'errors':errors,
            'historical_ci_failure':'2 IEEE118 seed81 jobs failed due to literal <=100 check against 100.00000000000001',
            'status':'PASS' if len(rows)==12 and not errors else 'FAIL'}
    (out/'semantic_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'rows':len(rows),'errors':errors}))
    return report['status']=='PASS'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raise SystemExit(0 if audit(a.input,a.out) else 2)
