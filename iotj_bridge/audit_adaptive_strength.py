#!/usr/bin/env python3
"""Fail-closed evidence audit for IoT-J R3 adaptive intensity matrix.

Independent statistical unit: entire training seed. Missing/duplicate seeds,
missing checkpoints, inconsistent score/weight arithmetic, or partial matrices
cause nonzero exit. No figure, reply or paper table is emitted on failure.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

SEEDS=(90,91,92,93,94)
STRENGTHS={"025":.25,"050":.5,"100":1.,"200":2.}
SCENARIOS=("clean","joint")+tuple(
    mode+"_"+tag for mode in ("adaptive_weight","adaptive_damage")
    for tag in STRENGTHS)+("adaptive_meta_100","adaptive_update_100","adaptive_proto_100")
DEFENSES=("uncapped","capped")
EXPECTED={(seed,defense,scenario) for seed in SEEDS for defense in DEFENSES
          for scenario in SCENARIOS}

def dump_csv(path,rows):
    if not rows:
        raise ValueError("cannot write empty table "+str(path))
    keys=sorted({k for row in rows for k in row})
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys)
        w.writeheader();w.writerows(rows)

def verify_close(a,b,msg,atol=2.e-5):
    if not math.isfinite(float(a)) or abs(float(a)-float(b))>atol*max(1.,abs(float(b))):
        raise ValueError(msg+": "+str(a)+" vs "+str(b))

def identify(s):
    attack=s["attack"]
    if attack in ("clean","joint"):
        scenario=attack
    else:
        value=float(s["attack_strength"])
        tag=min(STRENGTHS,key=lambda x:abs(STRENGTHS[x]-value))
        verify_close(value,STRENGTHS[tag],"strength",1.e-12)
        scenario=attack+"_"+tag
    cap=s["weight_cap"]
    defense="uncapped" if cap=="None" else "capped" if abs(float(cap)-.2)<1.e-12 else "invalid"
    return (int(s["seed"]),defense,scenario)

def bootstrap(vals,seed=20261110,reps=4000):
    v=np.asarray(vals,dtype=float)
    if len(v)!=len(SEEDS):
        raise ValueError("statistical unit count "+str(len(v)))
    rng=np.random.default_rng(seed)
    draws=rng.integers(0,len(v),size=(reps,len(v)))
    m=v[draws].mean(axis=1)
    return float(v.mean()),float(np.quantile(m,.025)),float(np.quantile(m,.975))

def audit_one(path):
    d=json.loads(path.read_text(encoding="utf-8"))
    s=d["summary"];key=identify(s);seed,defense,scenario=key
    if key not in EXPECTED:
        raise ValueError("unexpected trial "+str(key))
    if (int(s["case"])!=39 or int(s["clients"])!=10
        or int(s["train_episodes"])!=1000 or int(s["eval_episodes"])!=10
        or int(s["completed_rounds"])!=200 or int(s["batch_size"])!=256
        or s["method"]!="adv" or s["hetero"]!="dim"
        or float(s["kappa"])!=.2 or not bool(int(s["fixed_traffic"]))):
        raise ValueError("run protocol mismatch "+str(key))
    if len(d["rounds"])!=200 or len(d["train_episodes"])!=1000 or len(d["tests"])!=10:
        raise ValueError("full-budget trace mismatch "+str(key))
    bad_ids=set(int(x) for x in s["malicious_client_ids"])
    if bad_ids!=(set() if scenario=="clean" else {8,9}):
        raise ValueError("unexpected malicious client IDs "+str(key))
    manifest=path.with_suffix(".manifest.json")
    checkpoint=path.with_suffix(".pt")
    if not manifest.exists() or not checkpoint.exists():
        raise ValueError("missing manifest/checkpoint "+str(path))
    meta=json.loads(manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta["source_json_sha256"]:
        raise ValueError("JSON SHA256 mismatch "+str(path))
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=meta["checkpoint_sha256"]:
        raise ValueError("checkpoint SHA256 mismatch "+str(path))
    if int(meta["training_episodes_executed"])!=1000:
        raise ValueError("missing training budget "+str(key))
    verify_close(sum(r["uplink_bytes"] for r in d["rounds"]),s["uplink_bytes"],"bytes",0)
    if sum(int(t["safe_dwell5"]) for t in d["tests"])!=s["safe_dwell_successes"]:
        raise ValueError("held-out safe dwell mismatch")
    verify_close(float(np.mean([t["final_restored_pct"] for t in d["tests"]])),
                 s["mean_test_load_pct"],"restored test",1.e-9)
    verify_close(float(np.mean([t["average_restored_pct"] for t in d["tests"]])),
                 s["mean_test_load_auc_pct"],"test AUC",1.e-9)
    rounds=[];stats=[]
    for i,r in enumerate(d["rounds"]):
        if int(r["round"])!=i or len(r["per_client"])!=10:
            raise ValueError("incorrect round or client count")
        active=i>=1 and bool(bad_ids)
        clients=r["per_client"]
        if r["accepted"]!=sum(bool(x["accepted"]) for x in clients):
            raise ValueError("accepted-client count mismatch")
        if r["accepted"]:
            verify_close(sum(x["aggregation_weight"] for x in clients),1.,"total accepted weight")
        for c in clients:
            if not c["accepted"]:
                if abs(float(c["aggregation_weight"]))>1.e-8:
                    raise ValueError("rejected client with nonzero weight")
                continue
            score=float(c["utility_used"])/(float(c["update_norm_clipped"])+.001)*float(c["drift_penalty"])
            verify_close(score,c["credibility_score"],"scorer mismatch")
            if defense=="capped" and float(c["aggregation_weight"])>.200001:
                raise ValueError("weight cap exceeded")
        aggregate=sum(float(clients[j]["aggregation_weight"]) for j in bad_ids)
        verify_close(aggregate,r["malicious_weight"],"malicious weight")
        if active:
            for j in bad_ids:
                if not clients[j]["attack_active"]:
                    raise ValueError("missing attack phase")
                if scenario.startswith("adaptive_"):
                    info=clients[j].get("attack_search")
                    if not info or not info.get("search_prior_only"):
                        raise ValueError("missing adaptive optimizer provenance")
                    if info["candidate_count"]<1:
                        raise ValueError("zero candidate search")
                    if info["candidate_norm"]>min(1,float(s["attack_strength"]))*.075+1.e-5 if "candidate_norm" in info else False:
                        raise ValueError("candidate exceeds intensity budget")
                    if len(clients[j]["original_sparse_support"])!=len(clients[j]["forged_sparse_support"]):
                        raise ValueError("sparse budget mismatch")
        if active:
            rounds.append({"seed":seed,"defense":defense,"scenario":scenario,
                           "round":i+1,"malicious_weight":aggregate,
                           "malicious_accepted_fraction":sum(bool(clients[j]["accepted"]) for j in bad_ids)/len(bad_ids),
                           "mean_score_malicious":float(np.mean([clients[j]["credibility_score"] or 0 for j in bad_ids])),
                           "restored_training_pct":float(d["train_episodes"][min((i+1)*5-1,999)]["final_restored_pct"]),
                           "direction_norm":float(r["direction_norm"])})
        stats.append(aggregate)
    return key,s,rounds

def label(s):
    return s.replace("_","\\_")

def render_tex(rows):
    by={(x["defense"],x["scenario"]):x for x in rows}
    lines=[
      "% GENERATED ONLY AFTER COMPLETE R3 EXPERIMENT AND INDEPENDENT AUDIT.",
      "\\begin{table*}[t]",
      "\\centering\\small",
      "\\caption{Adaptive utility--prototype--sparse-update manipulation on IEEE 39-bus, ten clients and two colluding Byzantine clients. Each cell uses five independent training seeds, 1000 episodes per seed, and ten held-out episodes. Weight is the sum of accepted malicious weights, averaged over attack-active rounds; load degradation is paired with the same-defense clean control. This measures the original utility--drift weighting rule, not a Byzantine security guarantee.}",
      "\\label{tab:r3-adaptive-strength}",
      "\\begin{tabular}{llrrrr}",
      "\\hline",
      "Defense & Attack / strength & Load (\\%) & Safe dwell (\\%) & Malicious weight & Load loss (pp)\\\\",
      "\\hline"
    ]
    for defense in DEFENSES:
        for scenario in SCENARIOS:
            r=by[(defense,scenario)]
            lines.append("%s & %s & %.2f & %.1f & %.3f & %+.2f\\\\"%(
                defense, label(scenario),r["load_mean"],
                100*r["dwell_mean"],r["weight_mean"],r["load_loss_mean"]))
        lines.append("\\hline")
    lines.extend(["\\end{tabular}",
      "\\vspace{1mm}",
      "\\parbox{0.96\\textwidth}{\\footnotesize The detailed per-seed 95\\% bootstrap confidence intervals, accepted malicious-client fractions, roundwise weight trajectories, checkpoint checksums and original JSON logs accompany the audit archive.}",
      "\\end{table*}",""])
    return "\n".join(lines)

def replies(rows):
    by={(x["defense"],x["scenario"]):x for x in rows}
    worst={}
    for defense in DEFENSES:
        affected=[x for x in rows if x["defense"]==defense and x["scenario"].startswith("adaptive_")]
        worst[defense]=max(affected,key=lambda x:x["load_loss_mean"])
    u=worst["uncapped"];c=worst["capped"]
    en=(
      "# IoT-J R3 — Reviewer comment: adaptive credibility maximization\n\n"
      "We agree that random, scaled, sign-flipped, or fixed joint forgeries do not establish "
      "resistance to rule-aware adaptive weight manipulation. We therefore implemented attacks "
      "that jointly optimize sparse upload values/support, forged recovery utility and prototype "
      "vectors under the unchanged server validation and clipping rule. The attacker uses its own "
      "current upload, previously broadcast global changes/prototypes and its own earlier public "
      "aggregation weight, but no current honest-client private uploads or held-out recovery labels.\n\n"
      "The complete audited IEEE39 matrix uses N=10, M=2, five seeds (90–94), 1000 training "
      "episodes and ten held-out evaluations per seed, comparing clean, fixed joint spoofing, "
      "weight-only and damage-aware objectives across strengths 0.25/0.5/1/2. "
      "Utility-only, prototype-only and update-only interventions are separately tested at strength 1. "
      "We report paired held-out restored-load and safe-dwell degradation, accepted malicious-client "
      "fractions, aggregate malicious weight, roundwise distributions and per-seed bootstrap intervals.\n\n"
      "The largest *observed mean* paired restored-load shortfall among adaptive conditions was "
      "{:.2f} percentage points for {} (uncapped), with mean attack-phase malicious weight {:.3f}; "
      "under the separately labeled 0.20 per-client cap, it was {:.2f} percentage points "
      "for {}, with mean malicious weight {:.3f}. "
      "These are empirical outcomes on the specified quasi-static AC backend, not worst-case "
      "bounds, dynamic-grid safety certificates or Byzantine tolerance proofs. "
      "The intensity=2 condition can be constrained by clipping and utility caps, "
      "so more nominal intensity need not mean more effective submitted manipulation.\n\n"
      "We also distinguish the cited BRPPFL Byzantine/cloud-edge setting from our recovery-control "
      "setting, VFL+ vertical learning from our heterogeneous shared-backbone setting, and "
      "the two NOMA physical-layer secrecy works from federated poisoning.\n"
    ).format(u["load_loss_mean"],u["scenario"],u["weight_mean"],
             c["load_loss_mean"],c["scenario"],c["weight_mean"])
    zh=(
      "# IoT-J R3 — 审稿意见：自适应信誉权重操纵\n\n"
      "我们承认固定联合伪造和随机/缩放/翻转更新不足以证明抵抗以最大化权重为目标的自适应攻击。"
      "本轮在不修改服务器裁剪、验收和评分公式的条件下，联合搜索稀疏上传索引及数值、"
      "上报恢复效用和原型。攻击者仅使用自身当前上传、历史公开模型变化与原型、"
      "自身上一轮公开权重，不访问当轮诚实客户端私有数据与留出测试结果。\n\n"
      "IEEE39 完整审计矩阵为 N=10、M=2、5 个独立训练种子（90—94），"
      "每种子训练 1000 回合、独立评估 10 回合。"
      "比较无攻击、固定联合伪造、仅最大化权重及兼顾方向性破坏的自适应攻击；"
      "强度分别为 0.25、0.5、1、2，并在强度 1 下增加仅元数据、仅更新、"
      "仅原型的消融。按种子报告配对的恢复负荷损失、安全驻留变化、"
      "恶意客户端验收比例、被接受的合计权重和逐轮轨迹。\n\n"
      "未限权时，自适应条件中平均恢复负荷损失最大的是 {}，"
      "相对无攻击同协议条件的差值为 {:.2f} 个百分点，"
      "攻击期恶意客户端平均合计权重为 {:.3f}；"
      "单客户端 0.20 限权时，分别为 {}、{:.2f} 个百分点、{:.3f}。"
      "以上仅是指定准静态 AC 平台的实测结果，不构成最坏情况界、动态物理安全证明或 Byzantine 保证。"
      "当上报效用和更新范数被服务器上限截断时，标称强度增大不必然导致有效攻击增强。\n"
    ).format(u["scenario"],u["load_loss_mean"],u["weight_mean"],
             c["scenario"],c["load_loss_mean"],c["weight_mean"])
    return en,zh

def audit(root,out):
    root=Path(root);out=Path(out)
    records={};round_rows=[]
    paths=sorted(p for p in root.rglob("*.json")
                 if not p.name.endswith(".manifest.json") and p.name.endswith(".json"))
    failures=[]
    for path in paths:
        try:
            key,s,rounds=audit_one(path)
            if key in records:
                raise ValueError("duplicate trial "+str(key))
            records[key]=s;round_rows.extend(rounds)
        except Exception as exc:
            failures.append({"path":str(path),"error":str(exc)})
    missing=sorted(EXPECTED-set(records))
    unexpected=sorted(set(records)-EXPECTED)
    if failures or missing or unexpected:
        out.mkdir(parents=True,exist_ok=True)
        (out/"audit_failure.json").write_text(json.dumps(
            {"expected":len(EXPECTED),"valid":len(records),"missing":missing,
             "unexpected":unexpected,"errors":failures},indent=2,ensure_ascii=False)+"\n")
        raise ValueError("fail-closed R3 matrix audit: "+str(out/"audit_failure.json"))
    per_seed=[];summary=[]
    for defense in DEFENSES:
        for scenario in SCENARIOS:
            vals=[]
            for seed in SEEDS:
                s=records[(seed,defense,scenario)]
                clean=records[(seed,defense,"clean")]
                rr=[r for r in round_rows if r["seed"]==seed and r["defense"]==defense and r["scenario"]==scenario]
                mal_weight=float(np.mean([r["malicious_weight"] for r in rr])) if rr else 0.
                mal_acc=float(np.mean([r["malicious_accepted_fraction"] for r in rr])) if rr else 0.
                row={"seed":seed,"defense":defense,"scenario":scenario,
                     "load_pct":float(s["mean_test_load_pct"]),
                     "auc_pct":float(s["mean_test_load_auc_pct"]),
                     "dwell":float(s["safe_dwell_successes"])/s["test_count"],
                     "weight":mal_weight,"malicious_accepted_fraction":mal_acc,
                     "load_loss_pp":float(clean["mean_test_load_pct"]-s["mean_test_load_pct"]),
                     "auc_loss_pp":float(clean["mean_test_load_auc_pct"]-s["mean_test_load_auc_pct"]),
                     "dwell_loss_pp":100*(float(clean["safe_dwell_successes"])/clean["test_count"]-
                                          float(s["safe_dwell_successes"])/s["test_count"])}
                per_seed.append(row);vals.append(row)
            data={"defense":defense,"scenario":scenario,"n_seeds":len(vals)}
            for m,k in (("load","load_pct"),("auc","auc_pct"),("dwell","dwell"),
                        ("weight","weight"),("accepted","malicious_accepted_fraction"),
                        ("load_loss","load_loss_pp"),("auc_loss","auc_loss_pp"),
                        ("dwell_loss","dwell_loss_pp")):
                mean,lo,hi=bootstrap([z[k] for z in vals],seed=20261110+len(summary)*100+len(m))
                data.update({m+"_mean":mean,m+"_lo95":lo,m+"_hi95":hi})
            summary.append(data)
    out.mkdir(parents=True,exist_ok=True)
    dump_csv(out/"adaptive_per_seed.csv",per_seed)
    dump_csv(out/"adaptive_per_round.csv",round_rows)
    dump_csv(out/"adaptive_summary.csv",summary)
    (out/"AdaptiveStrengthResults.tex").write_text(render_tex(summary),encoding="utf-8")
    en,zh=replies(summary)
    (out/"Reviewer_Adaptive_EN.md").write_text(en,encoding="utf-8")
    (out/"Reviewer_Adaptive_ZH.md").write_text(zh,encoding="utf-8")
    metadata={"protocol":"IOTJ-R3-rule-aware-v1","expected_runs":len(EXPECTED),
              "audited_runs":len(records),"passed":True,
              "training_seeds":list(SEEDS),"episodes_per_seed":1000,
              "held_out_episodes_per_seed":10,"clients":10,"malicious_clients":2,
              "attack_start_round_zero_based":1,
              "independent_unit":"training seed","backend":"pandapower quasi-static AC",
              "not_demonstrated":"worst-case Byzantine robustness or dynamic physical invariance",
              "artifacts":[p.name for p in out.iterdir() if p.is_file()]}
    (out/"audit_report.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    return metadata

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.root,args.out),indent=2))
