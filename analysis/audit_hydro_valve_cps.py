#!/usr/bin/env python3
"""Independent integrity and metric audit for AEFC hydro-valve SIL traces.
This script reads archived traces only; it does not execute the plant model.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, tarfile
from pathlib import Path
import numpy as np

METHODS=("FedRL","RobustAgg","AEFC-no-PATBU","AEFC-no-Gate","AEFC-no-TGOPA","AEFC-no-Shield","AEFC-Full")
SCENARIOS=("clean","physical","knowledge","joint")


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def close(a,b,tol=1e-9):
    if a is None or b is None: return a is None and b is None
    return abs(float(a)-float(b)) <= tol*max(1.0,abs(float(a)),abs(float(b)))

def recompute(rows,cfg):
    steps=len(rows); states=np.asarray([r['state_true'] for r in rows],float)
    flow=np.abs(states[:,1:3]-np.asarray(cfg['q_ref'])[None,:]).mean()
    head=np.abs(states[:,0]-1.0).mean(); speed=np.abs(states[:,3]-1.0).mean()
    power=np.asarray([r['power_output'] for r in rows],float)
    pmae=np.abs(power-float(cfg['load_nominal'])).mean()
    bmax=max(float(r['belief_error']) for r in rows)
    theta0=np.asarray(cfg['theta_anchor'],float)
    tdrift=max(float(np.linalg.norm(np.asarray(r['theta_deployed'],float)-theta0)) for r in rows)
    sherr=np.asarray([float(r['theta_shadow_error']) for r in rows])
    post=[float(r['theta_shadow_error']) for r in rows if int(r['t'])>int(cfg['attack_end'])]
    first=float(post[0]) if post else None; last=float(post[-1]) if post else None
    correction=False; first_corr=None; start=int(cfg['attack_end'])+1; eps=float(cfg['epsilon']); hold=int(cfg['hold_points'])
    for k in range(max(0,len(post)-hold)):
        if first is not None and first>eps and post[k]>eps and np.all(np.asarray(post[k+1:k+1+hold])<=eps):
            correction=True; first_corr=start+k+1; break
    exec_l2=np.asarray([np.linalg.norm(np.asarray(r['valve_executed'])-np.asarray(r['valve_command'])) for r in rows])
    margins=[float(r['shield_margin']) for r in rows if r.get('shield_margin') is not None]
    return {
        'flow_mae':float(flow),'head_mae':float(head),'speed_mae':float(speed),'power_mae':float(pmae),
        'state_violation_points':sum(not bool(r['state_safe']) for r in rows),
        'actuator_saturation_points':sum(bool(r.get('actuator_saturated',False)) for r in rows),
        'shield_intervention_points':sum(bool(r['shield_intervened']) for r in rows),
        'shield_infeasible_points':sum(not bool(r.get('shield_feasible',True)) for r in rows),
        'gate_reject_points':sum(not bool(r['gate_allowed']) for r in rows),
        'accepted_updates':sum(bool(r['theta_update_accepted']) for r in rows),
        'max_belief_error':float(bmax),'max_theta_drift_from_anchor':float(tdrift),
        'max_dynamic_shadow_error':float(sherr.max()),
        'post_attack_initial_shadow_error':first,'post_attack_final_shadow_error':last,
        'post_attack_exposed':bool(first is not None and first>eps),
        'dynamic_shadow_correction':correction,'first_correction_step':first_corr,
        'mean_execution_l2':float(exec_l2.mean()),
        'mean_shield_margin':float(np.mean(margins)) if margins else None,
    }

def paired_bootstrap(rows_by_key, scenario, metric, method_a, method_b, nboot=20000, seed=20261030):
    a={r['seed']:r[metric] for (sc,m),rr in rows_by_key.items() if sc==scenario and m==method_a for r in rr}
    b={r['seed']:r[metric] for (sc,m),rr in rows_by_key.items() if sc==scenario and m==method_b for r in rr}
    seeds=sorted(set(a)&set(b)); dif=np.asarray([float(a[s])-float(b[s]) for s in seeds])
    rng=np.random.default_rng(seed+SCENARIOS.index(scenario)+METHODS.index(method_a)+METHODS.index(method_b))
    ix=rng.integers(0,len(dif),size=(nboot,len(dif)))
    boot=dif[ix].mean(axis=1)
    return {'scenario':scenario,'metric':metric,'difference_definition':f'{method_a} - {method_b}',
            'method_a':method_a,'method_b':method_b,'n_paired_seeds':len(seeds),
            'mean_paired_difference':float(dif.mean()),'median_paired_difference':float(np.median(dif)),
            'bootstrap_95_low':float(np.quantile(boot,0.025)),'bootstrap_95_high':float(np.quantile(boot,0.975))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); args=ap.parse_args()
    root=Path(args.input); manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    cfg=json.loads((root/'frozen_config.json').read_text(encoding='utf-8'))
    cfg_hash=hashlib.sha256((root/'frozen_config.json').read_bytes()).hexdigest()
    failures=[]
    if cfg_hash!=manifest['config_sha256']: failures.append('frozen_config SHA256 does not match manifest')
    seed_ids=list(range(int(manifest['seed_start']),int(manifest['seed_start'])+int(manifest['seeds'])))
    all_metrics=[]; rows_by_key={}; total_samples=0
    for scenario in SCENARIOS:
        for method in METHODS:
            key=(scenario,method); rows_by_key[key]=[]
            for seed in seed_ids:
                raw=root/scenario/method/f'seed_{seed}.jsonl'
                summ=root/scenario/method/f'seed_{seed}.summary.json'
                if not raw.exists() or not summ.exists():
                    failures.append(f'missing raw or summary: {scenario}/{method}/seed_{seed}'); continue
                try:
                    rows=[json.loads(line) for line in raw.read_text(encoding='utf-8').splitlines() if line.strip()]
                    sr=json.loads(summ.read_text(encoding='utf-8'))
                except Exception as e:
                    failures.append(f'parse error {raw}: {e}'); continue
                if len(rows)!=int(cfg['steps']): failures.append(f'{raw}: expected {cfg["steps"]} rows, got {len(rows)}')
                if [int(r['t']) for r in rows]!=list(range(int(cfg['steps']))): failures.append(f'{raw}: time index not contiguous')
                if any(r.get('seed')!=seed or r.get('method')!=method or r.get('scenario')!=scenario for r in rows):
                    failures.append(f'{raw}: seed/method/scenario metadata mismatch')
                calc=recompute(rows,cfg); total_samples+=len(rows)
                for k,v in calc.items():
                    if k in sr and not close(sr[k],v): failures.append(f'{summ}: {k} mismatch stored={sr[k]} recomputed={v}')
                if sr.get('config_sha256')!=cfg_hash: failures.append(f'{summ}: config hash mismatch')
                row={'seed':seed,'method':method,'scenario':scenario,**calc}
                all_metrics.append(row); rows_by_key[key].append(row)
    expected=int(manifest['episodes']); actual=len(all_metrics)
    if actual!=expected: failures.append(f'episode count mismatch expected={expected} audited={actual}')
    if total_samples!=int(manifest['samples']): failures.append(f'sample count mismatch expected={manifest["samples"]} audited={total_samples}')
    # Verify aggregate and seed summary files exist and contain the expected rows.
    for p,n in [('summary.csv',expected),('aggregate_by_method_scenario.csv',len(SCENARIOS)*len(METHODS))]:
        if not (root/p).exists(): failures.append(f'missing {p}')
        else:
            with (root/p).open(encoding='utf-8') as f: count=sum(1 for _ in csv.DictReader(f))
            if count!=n: failures.append(f'{p}: expected {n} rows, got {count}')
    # Paired effect estimates, using seeds as the resampling unit.
    paired=[]
    for sc in SCENARIOS:
        for comp in ('FedRL','RobustAgg','AEFC-no-PATBU','AEFC-no-Gate','AEFC-no-TGOPA','AEFC-no-Shield'):
            for metric in ('flow_mae','max_belief_error','max_theta_drift_from_anchor','state_violation_points'):
                paired.append(paired_bootstrap(rows_by_key,sc,metric,'AEFC-Full',comp))
    with (root/'per_seed_metrics.csv').open('w',newline='',encoding='utf-8') as f:
        cols=list(all_metrics[0].keys()); w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(all_metrics)
    with (root/'paired_effects.csv').open('w',newline='',encoding='utf-8') as f:
        cols=list(paired[0].keys()); w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(paired)
    # Immutable archive: all raw JSONL and per-seed summaries.
    archive=root/'raw-traces.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
        for sc in SCENARIOS:
            for method in METHODS:
                for seed in seed_ids:
                    for suffix in ('.jsonl','.summary.json'):
                        p=root/sc/method/f'seed_{seed}{suffix}'
                        if p.exists(): tar.add(p,arcname=str(p.relative_to(root)))
    archive_hash=sha256(archive)
    (root/'raw-traces.sha256').write_text(f'{archive_hash}  raw-traces.tar.gz\n',encoding='utf-8')
    report={'experiment':manifest['experiment'],'expected_episodes':expected,'audited_episodes':actual,
            'expected_samples':manifest['samples'],'audited_samples':total_samples,
            'raw_archive':'raw-traces.tar.gz','raw_archive_sha256':archive_hash,
            'config_sha256':cfg_hash,'all_checks_passed':not failures,'failures':failures,
            'interpretation':'SIL archive audit only; not physical hardware validation or G1/G3/G5 formal certification'}
    (root/'audit_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    md=['# AEFC 水力阀门流量调节 SIL 原始轨迹审计','',
        f'- 预期/复核回合：{expected}/{actual}',f'- 预期/复核采样点：{manifest["samples"]}/{total_samples}',
        f'- 配置 SHA256：`{cfg_hash}`',f'- 原始归档 SHA256：`{archive_hash}`',
        f'- 审计结果：**{"PASS" if not failures else "FAIL"}**','',
        '本审计仅验证SIL轨迹、摘要及归档完整性，不构成真实PLC/执行器实验，也不构成G1/G3/G5形式认证。']
    if failures: md+=['','## 未通过项']+['- '+x for x in failures]
    (root/'audit_summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if failures: raise SystemExit(2)

if __name__=='__main__': main()