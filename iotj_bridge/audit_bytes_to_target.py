#!/usr/bin/env python3
"""Independent censoring, checkpoint and serialized-byte audit for IoTJ BTT.

The auditor never trains a policy, never uses the final test set to choose a
checkpoint, and never converts 200-round endpoint bytes to bytes-to-target.
"""
import argparse,csv,hashlib,json,math,pathlib,sys

def sha256_file(path):
    h=hashlib.sha256()
    with path.open('rb') as fp:
        for blk in iter(lambda:fp.read(1024*1024),b''):
            h.update(blk)
    return h.hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def audit(root,*,require_full=False):
    root=pathlib.Path(root)
    btt=root/'btt'
    protocol=read_json(btt/'protocol.json')
    report=read_json(btt/'bytes_to_target_summary.json')
    original=read_json(root/'run.json')
    independent=read_json(btt/'independent_test.json')
    records=[json.loads(x) for x in (btt/'round_validation.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    manifest=[json.loads(x) for x in (btt/'checkpoint_manifest.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    error=[]
    def check(condition,why):
        if not condition:error.append(why)
    total=int(protocol['planned_rounds'])
    nval=int(protocol['validation_n'])
    ntest=int(protocol['test_n'])
    minpass=int(protocol['minimum_validation_successes'])
    assert nval==10 and minpass==9 and ntest==10
    if require_full:check(total==200,'Expected 200 full-budget rounds')
    check(len(records)==total+1,'Expected round0..roundN validation')
    check(len(manifest)==total+1,'Missing checkpoint hash manifest entries')
    check(len(original['rounds'])==total,'Missing original synchronized rounds')
    check(original['summary']['method']==protocol['method'],'Run method mismatch')
    check(original['summary']['attack']==protocol['attack'],'Run attack mismatch')
    check(original['summary']['case']==protocol['case'],'Grid case mismatch')
    check(original['summary']['seed']==protocol['seed'],'Training seed mismatch')
    check(original['summary']['train_episodes']==total*5,'Episode count mismatch')
    check(original['summary']['completed_rounds']==total,'Federated round count mismatch')
    check(set(protocol['validation_seeds']).isdisjoint(protocol['test_seeds']),'Validation/test seeds overlap')
    check(len(set(protocol['validation_seeds']))==nval,'Duplicate validation seeds')
    check(len(set(protocol['test_seeds']))==ntest,'Duplicate independent test seeds')
    check(bool(independent['selection_used_validation_only']),'Test-based selection claimed')
    check(independent['independent_test_seeds']==protocol['test_seeds'],'Test seed identity mismatch')
    check("serialized application" in protocol['cumulative_byte_scope'].lower(),'Measured byte scope missing')
    cumulative=0;first_joint=None;first_load=None
    checksums=[]
    for idx,rec in enumerate(records):
        check(rec['round_1based']==idx,'Round index mismatch')
        check(rec['training_episodes']==idx*5,'Training episode index mismatch')
        expected_uplink=0 if idx==0 else int(original['rounds'][idx-1]['uplink_bytes'])
        check(rec['uplink_round_bytes']==expected_uplink,f'Round {idx} serialized uplink mismatch')
        cumulative+=expected_uplink
        check(rec['cumulative_serialized_uplink_bytes']==cumulative,f'Round {idx} cumulative bytes mismatch')
        ckpt=btt/rec['checkpoint_file']
        check(ckpt.is_file(),f'Round {idx} checkpoint absent')
        if ckpt.is_file():
            digest=sha256_file(ckpt)
            check(digest==rec['checkpoint_sha256'],f'Round {idx} checkpoint sha256 mismatch')
            checksums.append((str(ckpt.relative_to(root)),digest))
        v=rec['validation_episodes']
        check(len(v)==nval,f'Round {idx} validation episode count mismatch')
        check([z['scenario_seed'] for z in v]==protocol['validation_seeds'],f'Round {idx} validation seed changes')
        joint_count=0;load_count=0
        for z in v:
            dwell_joint=0;dwell_load=0;hit_joint=False;hit_load=False
            for step in z['trace']:
                restored=float(step['restored_pct'])
                safe=bool(step['safe']) and bool(step['ac_converged']) and (
                    float(step['voltage_violation_pu_sum'])<=1e-7 and
                    float(step['thermal_excess_pct_sum'])<=1e-7)
                load=restored>=90.0
                dwell_load=dwell_load+1 if load else 0
                dwell_joint=dwell_joint+1 if load and safe else 0
                hit_joint |= dwell_joint>=5
                hit_load |= dwell_load>=5
            check(bool(z['joint_success'])==hit_joint,f'Round {idx} joint trace mismatch')
            check(bool(z['load_only_success'])==hit_load,f'Round {idx} load-only trace mismatch')
            joint_count+=int(hit_joint)
            load_count+=int(hit_load)
        check(rec['validation_joint_successes']==joint_count,f'Round {idx} joint successes mismatch')
        check(rec['validation_load_only_successes']==load_count,f'Round {idx} load successes mismatch')
        check(bool(rec['validation_joint_target_met'])==(joint_count>=minpass),f'Round {idx} joint event mismatch')
        check(bool(rec['validation_load_only_target_met'])==(load_count>=minpass),f'Round {idx} load event mismatch')
        if joint_count>=minpass and first_joint is None:first_joint=idx
        if load_count>=minpass and first_load is None:first_load=idx
    check(report['final_cumulative_serialized_uplink_bytes']==cumulative,'Report terminal traffic mismatch')
    check(original['summary']['uplink_bytes']==cumulative,'Original strict-run traffic mismatch')
    for key,index in [('joint',first_joint),('load_only',first_load)]:
        target=report[key+'_target']
        check(target['event_observed']==(index is not None),f'{key} event flag mismatch')
        check(target['bytes_to_target']==(None if index is None else records[index]['cumulative_serialized_uplink_bytes']),f'{key} first-hit bytes mismatch')
        check(target['right_censored_at_round']==(total if index is None else None),f'{key} censor mismatch')
        check(target['observed_endpoint_budget_bytes']==cumulative,f'{key} endpoint mismatch')
    expected_evals={'terminal':total}
    if first_joint is not None:expected_evals['first_validation_joint']=first_joint
    if first_load is not None:expected_evals['first_validation_load_only']=first_load
    check(independent['checkpoints'].keys()==expected_evals.keys(),'Missing/extra independent test checkpoints')
    for name,idx in expected_evals.items():
        if name not in independent['checkpoints']:continue
        t=independent['checkpoints'][name]
        check(t['checkpoint_round_1based']==idx,f'{name} selected checkpoint mismatch')
        check(t['checkpoint_sha256']==records[idx]['checkpoint_sha256'],f'{name} test checkpoint hash mismatch')
        check([z['scenario_seed'] for z in t['episodes']]==protocol['test_seeds'],f'{name} test seeds mismatch')
        check(len(t['episodes'])==ntest,f'{name} test count mismatch')
        check(t['joint_successes']==sum(int(z['joint_success']) for z in t['episodes']),f'{name} joint test count mismatch')
        check(t['load_only_successes']==sum(int(z['load_only_success']) for z in t['episodes']),f'{name} load test count mismatch')
    return {'case':protocol['case'],'attack':protocol['attack'],'seed':protocol['seed'],
            'method':protocol['method'],'rounds':total,
            'validation_scenarios':nval,'independent_test_scenarios':ntest,
            'checkpoint_count':len(records),'checkpoint_hashes_verified':len(checksums),
            'bytes_observed_at_200_rounds':cumulative if total==200 else None,
            'bytes_observed_at_endpoint':cumulative,
            'full_target_event_observed':int(first_joint is not None),
            'full_target_first_round':first_joint,
            'full_target_bytes':None if first_joint is None else records[first_joint]['cumulative_serialized_uplink_bytes'],
            'full_target_right_censored':int(first_joint is None),
            'load_target_event_observed':int(first_load is not None),
            'load_target_first_round':first_load,
            'load_target_bytes':None if first_load is None else records[first_load]['cumulative_serialized_uplink_bytes'],
            'load_target_right_censored':int(first_load is None),
            'independent_test_selected':{k:{'round':v['checkpoint_round_1based'],
                'joint_successes':v['joint_successes'],
                'load_only_successes':v['load_only_successes']} for k,v in independent['checkpoints'].items()},
            'measured_traffic_scope':'instrumented serialized application uplink (NOT network-wire bytes)',
            'errors':error,'valid':not error}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--require-full',action='store_true')
    a=p.parse_args()
    inputs=sorted(a.input.rglob('bytes_to_target_summary.json'))
    if not inputs:raise SystemExit('No frozen bytes-to-target experiment folders')
    rows=[]
    for path in inputs:
        root=path.parent.parent
        try:rows.append(audit(root,require_full=a.require_full))
        except Exception as exc:
            rows.append({'path':str(root),'valid':False,'errors':[f'{type(exc).__name__}: {exc}']})
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'per_run_audit.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    fields=['case','attack','seed','method','rounds','checkpoint_count',
            'checkpoint_hashes_verified','bytes_observed_at_endpoint',
            'full_target_event_observed','full_target_first_round','full_target_bytes',
            'full_target_right_censored','load_target_event_observed',
            'load_target_first_round','load_target_bytes','load_target_right_censored',
            'valid']
    with (a.out/'per_run_summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    overall={'valid':all(r['valid'] for r in rows),'valid_runs':sum(r['valid'] for r in rows),
             'total_runs':len(rows),'failures':[{k:r.get(k) for k in ('case','attack','seed','method','path','errors')}
             for r in rows if not r['valid']]}
    (a.out/'audit_summary.json').write_text(json.dumps(overall,indent=2)+'\n')
    print(json.dumps(overall))
    if not overall['valid']:raise SystemExit(2)
if __name__=='__main__':main()
