#!/usr/bin/env python3
"""Second-pass audit for published Fig5/6 AC evidence (never alters training).

Independently reads the committed 50,000-episode CSV, the downloadable
compressed step log from the archived original Actions run, and all
seed-level and per-episode aggregates. This is not a native Simulink audit.
"""
import argparse,csv,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path

MODES={"adv","ordinary","adv_no_cw","dense","dense_cw"}
SEEDS=set(range(80,90))
N=50000

def must(test,reason):
    if not test:raise AssertionError(reason)

def near(a,b,reason,rtol=1e-7):
    a,b=float(a),float(b)
    must(math.isfinite(a) and math.isfinite(b) and
         abs(a-b)<=rtol*max(1,abs(a),abs(b)),reason+f": {a} != {b}")

def rows(path):
    with Path(path).open(encoding="utf-8",newline="") as f:
        yield from csv.DictReader(f)

def run(committed,archive,out):
    committed=Path(committed);archive=Path(archive);out=Path(out)
    report=json.loads((committed/"fig56_audit_report.json").read_text())
    must(report["passed"] is True and report["audited_runs"]==50,"first audit status")
    must(report["source_git_commits"]==["0af6e066ff385b191b2db3b86a40adc2ad79956f"],"frozen source SHA")
    full={}
    groups=defaultdict(list)
    groups_episode=defaultdict(list)
    for ep in rows(committed/"fig56_per_episode.csv"):
        key=(ep["mode"],int(ep["seed"]),int(ep["episode"]))
        must(key not in full,"duplicate episode key "+str(key))
        must(key[0] in MODES and key[1] in SEEDS and 1<=key[2]<=1000,"invalid episode key")
        must(ep["git_commit"]==report["source_git_commits"][0],"wrong training SHA")
        must(1<=int(ep["observed_steps"])<=30,"invalid steps executed")
        must(int(ep["recovery_reached"])==1-int(ep["right_censored"]),"recovery/censor disagreement")
        must((int(ep["first_safe_dwell_start_step"])<0)==bool(int(ep["right_censored"])),"recovery label mismatch")
        near(ep["restricted_recovery_score"],
             ep["first_safe_dwell_start_step"] if int(ep["recovery_reached"]) else 31,
             "restricted score")
        must(0<=float(ep["terminal_restored_load_pct"])<=100.00001,"invalid accuracy")
        full[key]=ep
        groups[key[:2]].append(ep)
        groups_episode[(key[0],key[2])].append(ep)
    must(len(full)==N,"expected 50,000 real episodes, got "+str(len(full)))
    must(len(groups)==50 and all(len(v)==1000 for v in groups.values()),"per-seed count")
    must(len(groups_episode)==5000 and all(len(v)==10 for v in groups_episode.values()),"per-episode seed count")
    gz=list(archive.rglob("fig56_per_step.csv.gz"))
    must(len(gz)==1,"expected one archived gz step log; found "+str(gz))
    step_path=gz[0]
    counts=defaultdict(int);first={};streak=defaultdict(int);terminal={};step_total=0
    with gzip.open(step_path,"rt",encoding="utf-8",newline="") as f:
        for z in csv.DictReader(f):
            key=(z["mode"],int(z["seed"]),int(z["episode"]))
            must(key in full,"step without matching episode "+str(key))
            t=int(z["step"])
            must(t==counts[key]+1,"missing/duplicate step "+str(key))
            counts[key]+=1;step_total+=1
            load=float(z["restored_pct"])
            must(0<=load<=100.00001,"invalid physical load")
            ok=bool(int(z["safe"])) and bool(int(z["ac_converged"])) and load>=90.
            streak[key]=streak[key]+1 if ok else 0
            if streak[key]>=5 and key not in first:first[key]=t-4
            terminal[key]=load
    must(len(counts)==N,"missing per-step physical episode")
    for key,ep in full.items():
        must(counts[key]==int(ep["observed_steps"]),"number of physical steps mismatch "+str(key))
        must(first.get(key,-1)==int(ep["first_safe_dwell_start_step"]),"first-five-safe-step mismatch "+str(key))
        near(terminal[key],ep["terminal_restored_load_pct"],"terminal load mismatch")
    seed_table=list(rows(committed/"fig56_per_seed.csv"))
    must(len(seed_table)==50,"seed summary row count")
    for s in seed_table:
        key=(s["mode"],int(s["seed"]))
        must(key in groups,"unmatched seed in summary")
        es=groups[key]
        near(sum(float(z["terminal_restored_load_pct"]) for z in es)/1000,
             s["mean_terminal_restored_pct"],"seed terminal load")
        near(sum(float(z["recovery_reached"]) for z in es)/1000,
             s["safe_dwell_success_fraction"],"seed recovery fraction")
        near(sum(float(z["restricted_recovery_score"]) for z in es)/1000,
             s["mean_restricted_recovery_score"],"seed restricted score")
        must(sum(int(z["right_censored"]) for z in es)==int(s["failed_or_censored_count"]),
             "seed censored count")
    curves=list(rows(committed/"fig56_per_episode_seed_mean.csv"))
    must(len(curves)==5000,"5,000 curve rows")
    for z in curves:
        key=(z["mode"],int(z["episode"]))
        must(key in groups_episode,"unmatched aggregated episode")
        es=groups_episode[key]
        near(sum(float(x["terminal_restored_load_pct"]) for x in es)/10,
             z["mean_terminal_restored_load_pct"],"curve accuracy")
        near(sum(float(x["restricted_recovery_score"]) for x in es)/10,
             z["mean_restricted_recovery_score"],"curve recovery score")
        near(sum(float(x["recovery_reached"]) for x in es)/10,
             z["safe_dwell_fraction"],"curve safe success fraction")
        must(sum(int(x["right_censored"]) for x in es)==int(z["n_censored"]),"curve censor count")
    ssummary=list(rows(committed/"fig56_seed_summary.csv"))
    must(len(ssummary)==5,"five method summary rows")
    for r in ssummary:
        key=r["mode"]
        v=[t for t in seed_table if t["mode"]==key]
        must(len(v)==10 and int(r["independent_seeds"])==10,"summary seeds")
        near(sum(float(x["mean_terminal_restored_pct"]) for x in v)/10,
             r["mean_terminal_restored_pct_mean"],"summary mean accuracy")
        near(sum(float(x["safe_dwell_success_fraction"]) for x in v)/10,
             r["safe_dwell_success_fraction_mean"],"summary safe fraction")
        near(sum(float(x["mean_restricted_recovery_score"]) for x in v)/10,
             r["mean_restricted_recovery_score_mean"],"summary restricted score")
    for name in ("fig5_ieee39_ac_supplement.png","fig6_ieee39_ac_supplement.png"):
        must((committed/name).is_file() and (committed/name).stat().st_size>10000,
             "missing supplementary plot "+name)
    sha=hashlib.sha256()
    with step_path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            sha.update(part)
    outcome={
        "passed":True,"source_run":42940416216,"source_commit":report["source_git_commits"][0],
        "total_run_jobs":50,"validated_per_episode_rows":len(full),
        "validated_per_step_rows":step_total,"episodes_with_step_data":len(counts),
        "validated_seed_summary_rows":len(seed_table),"validated_episode_curve_rows":len(curves),
        "validated_methods":sorted(MODES),"validated_seeds":sorted(SEEDS),
        "step_log_sha256":sha.hexdigest(),"original_simulink_figures_reproduced":False
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/"fig56_second_pass_verification.json").write_text(
        json.dumps(outcome,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(outcome,indent=2))
    return outcome

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--committed",type=Path,required=True)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    run(a.committed,a.archive,a.out)
