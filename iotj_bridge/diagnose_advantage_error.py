#!/usr/bin/env python3
"""Paired physical rollout diagnostic of estimated local recovery advantages.

This measures the finite-horizon current-policy advantage proxy, NOT the
unknown optimal Q* or a uniform critic-error certificate. Checkpoints are
loaded without changing their weights or training data. All diagnostic
demand profiles are disjoint from both training and held-out evaluations.
"""
from __future__ import annotations
import argparse,copy,csv,hashlib,json,math
from pathlib import Path
import numpy as np
import torch
try:
    from .strict_run import RecoveryGrid
    from .strict_agent import Agent
except ImportError:
    from strict_run import RecoveryGrid
    from strict_agent import Agent

STATE_TIMES=(0,10)
PROFILES=(0,1)
ACTION_PERTURBATIONS=(-.12,+.12)

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def policy_actions(agents,obs):
    with torch.no_grad():
        return [float(a.actor(torch.tensor(np.asarray(o,dtype=np.float32)[None,:]))[0,0])
                for a,o in zip(agents,obs)]
def q_value(agent,obs,action):
    z=torch.tensor(np.concatenate([np.asarray(obs,dtype=np.float32),[action]])
                   [None,:],dtype=torch.float32)
    with torch.no_grad():return float(agent.critic(z).flatten()[0])
def policy_rollout(snapshot,agents,first_actions,gamma=.99):
    # Paired trajectories differ ONLY in the first chosen local action.
    # Grid stores imported pandapower module (snapshot.pp), which cannot be deepcopied.
    # Clone only mutable simulator state, keeping the module object shared.
    model=copy.copy(snapshot)
    model.net=copy.deepcopy(snapshot.net)
    model.served=snapshot.served.copy()
    model.demand=snapshot.demand.copy()
    model.vm=snapshot.vm.copy()
    model.violations=copy.deepcopy(snapshot.violations)
    model.obs_cache=copy.deepcopy(snapshot.obs_cache)
    model._delay_history=copy.deepcopy(getattr(snapshot,'_delay_history',[]))
    model.rng=np.random.default_rng()
    model.rng.bit_generator.state=copy.deepcopy(snapshot.rng.bit_generator.state)
    obs=model.observations()
    discount=1.
    returns=np.zeros(len(agents),dtype=np.float64)
    n=0
    while True:
        action=first_actions if n==0 else policy_actions(agents,obs)
        obs,rewards,done,_=model.step(action)
        returns+=discount*np.asarray(rewards,dtype=np.float64)
        discount*=gamma;n+=1
        if done:break
    return returns,n
def load_checkpoint(p):
    p=Path(p)
    data=json.loads(p.read_text())
    s=data["summary"]
    assert s["method"]=="adv" and s["case"]==39 and s["hetero"]=="dim"
    assert s["train_episodes"]==1000 and s["completed_rounds"]==200
    m=p.with_suffix(".manifest.json");ck=p.with_suffix(".pt")
    provenance=json.loads(m.read_text())
    assert sha(p)==provenance["source_json_sha256"]
    assert sha(ck)==provenance["checkpoint_sha256"]
    obj=torch.load(ck,map_location="cpu",weights_only=False)
    assert int(obj["seed"])==int(s["seed"]) and obj["method"]=="adv"
    return data,s,obj,provenance
def evaluate(p):
    torch.set_num_threads(1)
    data,s,ckpt,prov=load_checkpoint(p)
    seed=int(s["seed"]); obs_dims=(6,3,6,3,6)
    agents=[]
    for j,dim in enumerate(obs_dims):
        agent=Agent(obs_dim=dim,seed=seed*100+j,
                    hidden=int(s["hidden_size"]),latent=int(s["latent_size"]),
                    batch=int(s["batch_size"]))
        agent.actor.load_state_dict(ckpt["actors"][j],strict=True)
        agent.critic.load_state_dict(ckpt["critics"][j],strict=True)
        agents.append(agent)
    rows=[]
    for profile in PROFILES:
        # No overlap with train seed and 100000+seed*100 test profiles.
        demand_seed=200000+seed*100+profile
        env=RecoveryGrid(39,len(agents),demand_seed,"dim",attack="clean")
        obs=env.reset()
        for t in range(max(STATE_TIMES)+1):
            if t in STATE_TIMES:
                ref_actions=policy_actions(agents,obs)
                baseline,base_steps=policy_rollout(env,agents,ref_actions)
                for i in range(len(agents)):
                    for perturb in ACTION_PERTURBATIONS:
                        a=np.asarray(ref_actions,dtype=np.float64).copy()
                        a[i]=np.clip(a[i]+perturb,
                                     float(agents[i].actor.lo),
                                     float(agents[i].actor.hi))
                        effect=float(a[i]-ref_actions[i])
                        if abs(effect)<1.e-10:
                            continue
                        damaged,d_steps=policy_rollout(env,agents,a)
                        qhat_ref=q_value(agents[i],obs[i],ref_actions[i])
                        qhat_pert=q_value(agents[i],obs[i],a[i])
                        estimate=qhat_pert-qhat_ref
                        physical=float(damaged[i]-baseline[i])
                        rows.append({
                          "seed":seed,"client_id":i,"profile":profile,
                          "physical_seed":demand_seed,"start_step":t,
                          "action_perturbation_requested":perturb,
                          "action_perturbation_realized":effect,
                          "qhat_behavior":qhat_pert,"qhat_policy":qhat_ref,
                          "mc_return_behavior":float(damaged[i]),
                          "mc_return_policy":float(baseline[i]),
                          "estimated_advantage":estimate,
                          "paired_finite_horizon_advantage":physical,
                          "estimated_minus_paired":estimate-physical,
                          "abs_adv_error":abs(estimate-physical),
                          "estimated_positive":int(estimate>0),
                          "paired_positive":int(physical>0),
                          "false_positive_advantage":int(estimate>0 and physical<=0),
                          "sign_mismatch":int((estimate>0)!=(physical>0)),
                          "near_estimated_zero_001":int(abs(estimate)<=.01),
                          "near_estimated_zero_005":int(abs(estimate)<=.05),
                          "near_estimated_zero_010":int(abs(estimate)<=.10),
                          "paired_horizon_remaining":min(base_steps,d_steps),
                          "checkpoint_train_episodes":int(s["train_episodes"]),
                          "source_json_sha256":prov["source_json_sha256"],
                          "checkpoint_sha256":prov["checkpoint_sha256"],
                          "source_git_commit":prov["git_commit"],
                          "estimand":"finite-horizon Q^pi(s,a)-Q^pi(s,pi(s)) under deterministic AC profile",
                        })
            if t==max(STATE_TIMES):break
            actions=policy_actions(agents,obs)
            obs,_,done,_=env.step(actions)
            if done:break
    if not rows:raise ValueError("No paired physical rollout diagnostics")
    d={
      "seed":seed,"source_git_commit":prov["git_commit"],
      "checkpoint_sha256":prov["checkpoint_sha256"],
      "samples":len(rows),"profiles":list(PROFILES),
      "state_steps":list(STATE_TIMES),
      "n_clients":len(agents),"finite_horizon":30,
      "mean_abs_advantage_error":float(np.mean([r["abs_adv_error"] for r in rows])),
      "false_positive_fraction":float(np.mean([r["false_positive_advantage"] for r in rows])),
      "sign_mismatch_fraction":float(np.mean([r["sign_mismatch"] for r in rows])),
      "near_zero_fraction_abs_est_le_001":float(np.mean([r["near_estimated_zero_001"] for r in rows])),
      "near_zero_fraction_abs_est_le_005":float(np.mean([r["near_estimated_zero_005"] for r in rows])),
      "near_zero_fraction_abs_est_le_010":float(np.mean([r["near_estimated_zero_010"] for r in rows])),
      "mean_estimated_advantage":float(np.mean([r["estimated_advantage"] for r in rows])),
      "mean_paired_advantage":float(np.mean([r["paired_finite_horizon_advantage"] for r in rows])),
      "max_empirical_abs_advantage_error":float(max(r["abs_adv_error"] for r in rows)),
      "global_error_guarantee":False,
      "limitation":"finite-horizon deterministic paired surrogate Q^pi; not true Q* or formal uniform epsilon_Q",
    }
    return rows,d
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    rows,s=evaluate(args.input)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    args.out.with_suffix(".summary.json").write_text(json.dumps(s,indent=2)+"\n")
    print(json.dumps(s,indent=2))
if __name__=="__main__":main()
