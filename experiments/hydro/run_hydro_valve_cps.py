#!/usr/bin/env python3
"""AEFC hydroelectric valve-flow CPS software-in-the-loop experiment.
Normalized, uncalibrated SIL model only; no physical PLC or actuator I/O.
AC1 and AC2 are valve-opening flow-regulation actuators.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

SCENARIOS=("clean","physical","knowledge","joint")
METHODS=("FedRL","RobustAgg","AEFC-no-PATBU","AEFC-no-Gate","AEFC-no-TGOPA","AEFC-no-Shield","AEFC-Full")

@dataclass(frozen=True)
class Config:
    steps:int=480; seed_start:int=220; seeds:int=20; dt:float=0.05
    attack_start:int=120; attack_end:int=239; clients:int=5; byzantine:int=1
    q_ref:tuple=(0.48,0.42); q_coeff:tuple=(0.58,0.52)
    q_tau:float=0.35; valve_tau:float=0.25; valve_rate:float=0.70
    reservoir_area:float=15.0; turbine_eta:float=0.92; turbine_inertia:float=0.65
    turbine_damping:float=0.45; qin_nominal:float=0.90; load_nominal:float=0.828
    observation_scales:tuple=(0.08,0.10,0.10,0.03,0.25,0.25)
    state_lower:tuple=(0.92,0.38,0.33,0.97,0.0,0.0)
    state_upper:tuple=(1.08,0.58,0.51,1.03,1.0,1.0)
    shield_reserve:tuple=(0.005,0.015,0.015,0.005,0.02,0.02)
    command_attack_bound:float=0.08; qin_uncertainty:float=0.004; load_uncertainty:float=0.006
    sensor_noise_bound:float=0.010; client_noise_bound:float=0.018; update_noise_bound:float=0.004
    physical_observation_bias:tuple=(0.28,0.42,-0.38,0.24,-0.18,0.18)
    replay_delay:int=4; replay_weight:float=0.65
    byzantine_evidence_bias:tuple=(1.4,-1.1,1.0,-0.8,0.9,-0.9)
    byzantine_gradient_scale:float=3.5; byzantine_gradient_bias:tuple=(0.20,-0.10,-0.18,0.09)
    patbu_prior_weight:float=0.20; patbu_observation_weight:float=0.15; patbu_evidence_weight:float=0.65
    patbu_age_decay:float=0.15; patbu_residual_scale:float=0.45
    gate_disagreement_weight:float=0.025; gate_spread_weight:float=0.010
    eta:float=0.010; clip_norm:float=0.020; trust_region:float=0.005
    q_min:float=0.90; risk_max:float=0.004; validation_slack:float=1e-7
    theta_initial:tuple=(0.90,0.055,0.90,0.055)
    theta_anchor:tuple=(0.90,0.055,0.90,0.055)
    theta_reference:tuple=(0.92,0.060,0.88,0.055)
    epsilon:float=0.001; hold_points:int=20

class HydroPlant:
    def __init__(self,c):
        self.c=c
        self.reset()
    def reset(self):
        c=self.c
        self.x=np.array([1.0,0.46,0.40,0.995,0.46/c.q_coeff[0],0.40/c.q_coeff[1]],float)
        return self.x.copy()
    def step(self,u,qin,load,post=None):
        c=self.c; post=np.zeros(2) if post is None else np.asarray(post,float)
        ue=np.clip(np.asarray(u,float)+post,0.0,1.0)
        h,q1,q2,w,a1,a2=self.x; a=np.array([a1,a2])
        rate=np.clip((ue-a)/c.valve_tau,-c.valve_rate,c.valve_rate)
        an=np.clip(a+c.dt*rate,0.0,1.0)
        qss=np.array(c.q_coeff)*an*math.sqrt(max(h,0.2))
        qn=np.maximum(np.array([q1,q2])+c.dt/c.q_tau*(qss-np.array([q1,q2])),0.0)
        hn=h+c.dt*(qin-float(qn.sum()))/c.reservoir_area
        pm=c.turbine_eta*hn*float(qn.sum())
        wn=w+c.dt/c.turbine_inertia*(pm-load-c.turbine_damping*(w-1.0))
        self.x=np.array([hn,qn[0],qn[1],wn,an[0],an[1]])
        return self.x.copy()
    def power(self):
        return self.c.turbine_eta*self.x[0]*(self.x[1]+self.x[2])

def norm_state(x,c):
    base=np.array([1.0,c.q_ref[0],c.q_ref[1],1.0,c.q_ref[0]/c.q_coeff[0],c.q_ref[1]/c.q_coeff[1]])
    return (np.asarray(x)-base)/np.asarray(c.observation_scales)
def denorm_state(z,c):
    base=np.array([1.0,c.q_ref[0],c.q_ref[1],1.0,c.q_ref[0]/c.q_coeff[0],c.q_ref[1]/c.q_coeff[1]])
    return base+np.asarray(z)*np.asarray(c.observation_scales)
def safe_state(x,c):
    return bool(np.all(np.asarray(x)>=np.asarray(c.state_lower)-1e-12) and np.all(np.asarray(x)<=np.asarray(c.state_upper)+1e-12))
def make_tape(seed,c):
    rng=np.random.default_rng(seed); t=np.arange(c.steps)
    return {
      "qin":c.qin_nominal+0.0025*np.sin(0.031*t+seed*0.13)+rng.normal(0,0.0008,c.steps),
      "load":c.load_nominal+0.0040*np.sin(0.023*t+seed*0.07+0.4)+rng.normal(0,0.0010,c.steps),
      "sensor":rng.uniform(-c.sensor_noise_bound,c.sensor_noise_bound,(c.steps,6)),
      "client":rng.uniform(-c.client_noise_bound,c.client_noise_bound,(c.steps,c.clients,6)),
      "update":rng.uniform(-c.update_noise_bound,c.update_noise_bound,(c.steps,c.clients,4)),
      "cmd_sign":rng.choice(np.array([-1.0,1.0]),size=(c.steps,2))}
def attack_active(t,c): return c.attack_start<=t<=c.attack_end
def obs_attack(z,t,hist,seed,c):
    if not attack_active(t,c): return z.copy()
    sign=-1.0 if seed%2 else 1.0
    bias=sign*np.asarray(c.physical_observation_bias)
    if t<c.attack_start+60: return z+bias
    replay=hist[max(0,t-c.replay_delay)]
    return c.replay_weight*replay+(1-c.replay_weight)*z+bias*0.25
def client_reports(z,t,tape,scenario,c):
    reports=z[None,:]+tape["client"][t]; ages=np.zeros(c.clients)
    if scenario in ("knowledge","joint") and attack_active(t,c):
        j=c.clients-1; reports[j]+=np.asarray(c.byzantine_evidence_bias); ages[j]=4.0
    return reports,ages
def trimmed_mean(values,f):
    a=np.sort(np.asarray(values),axis=0)
    if a.shape[0]<=2*f: raise ValueError("n_valid must be greater than 2f")
    return np.mean(a[f:a.shape[0]-f],axis=0) if f else np.mean(a,axis=0)
def local_gradient(theta,report,integral,c):
    h,q1,q2,w,a1,a2=denorm_state(report,c)
    e=np.array([c.q_ref[0]-q1+0.08*(1-h)+0.03*(1-w),c.q_ref[1]-q2+0.08*(1-h)+0.03*(1-w)])
    base=np.asarray(c.q_ref)/np.asarray(c.q_coeff)
    u=np.clip(np.array([base[0]+theta[0]*e[0]+theta[1]*integral[0],base[1]+theta[2]*e[1]+theta[3]*integral[1]]),0,1)
    a=np.array([a1,a2]); raw=(u-a)/c.valve_tau
    an=np.clip(a+c.dt*np.clip(raw,-c.valve_rate,c.valve_rate),0,1)
    qn=np.array([q1,q2])+c.dt/c.q_tau*(np.asarray(c.q_coeff)*an*math.sqrt(max(h,0.2))-np.array([q1,q2]))
    grad=np.zeros(4)
    for i,(kp,ki) in enumerate(((0,1),(2,3))):
        if abs(raw[i])<c.valve_rate and 0<an[i]<1:
            dq=c.dt/c.q_tau*c.q_coeff[i]*math.sqrt(max(h,0.2))
            grad[kp]=(qn[i]-c.q_ref[i])*dq*c.dt/c.valve_tau*e[i]
            grad[ki]=(qn[i]-c.q_ref[i])*dq*c.dt/c.valve_tau*integral[i]
    grad+=2e-4*(theta-np.asarray(c.theta_reference))
    return grad
def controller(z,theta,integral,c):
    h,q1,q2,w,a1,a2=denorm_state(z,c)
    e=np.array([c.q_ref[0]-q1+0.08*(1-h)+0.03*(1-w),c.q_ref[1]-q2+0.08*(1-h)+0.03*(1-w)])
    base=np.asarray(c.q_ref)/np.asarray(c.q_coeff)
    u=np.clip(np.array([base[0]+theta[0]*e[0]+theta[1]*integral[0],base[1]+theta[2]*e[1]+theta[3]*integral[1]]),0,1)
    return u,e
def predict_next(x,u,qin,load,c,post):
    h,q1,q2,w,a1,a2=np.asarray(x,float); ue=np.clip(np.asarray(u)+post,0,1)
    a=np.array([a1,a2]); an=np.clip(a+c.dt*np.clip((ue-a)/c.valve_tau,-c.valve_rate,c.valve_rate),0,1)
    qss=np.asarray(c.q_coeff)*an*math.sqrt(max(h,0.2))
    qn=np.maximum(np.array([q1,q2])+c.dt/c.q_tau*(qss-np.array([q1,q2])),0)
    hn=h+c.dt*(qin-float(qn.sum()))/c.reservoir_area
    pm=c.turbine_eta*hn*float(qn.sum())
    wn=w+c.dt/c.turbine_inertia*(pm-load-c.turbine_damping*(w-1))
    return np.array([hn,qn[0],qn[1],wn,an[0],an[1]])
def robust_shield(xhat,proposed,fallback,c):
    lo=np.asarray(c.state_lower)+np.asarray(c.shield_reserve); hi=np.asarray(c.state_upper)-np.asarray(c.shield_reserve)
    m=c.command_attack_bound; target=np.clip(np.asarray(proposed),m,1-m)
    corners=[np.array([a,b]) for a in (-m,m) for b in (-m,m)]
    def feasible(u):
        ms=[]
        for post in corners:
            xn=predict_next(xhat,u,c.qin_nominal-c.qin_uncertainty,c.load_nominal+c.load_uncertainty,c,post)
            ms.extend((xn-lo).tolist()); ms.extend((hi-xn).tolist())
        return min(ms)>=-1e-10,min(ms)
    ok,margin=feasible(target)
    if ok: return target,bool(np.linalg.norm(target-proposed)>1e-10),True,float(margin)
    grid=np.linspace(m,1-m,13); best=None; bestdist=float("inf"); bestmargin=float("-inf")
    for a in grid:
        for b in grid:
            cand=np.array([a,b]); ok,cm=feasible(cand)
            if ok:
                dist=float(np.linalg.norm(cand-proposed))
                if dist<bestdist: best,bestdist,bestmargin=cand,dist,float(cm)
    if best is not None: return best,True,True,bestmargin
    backup=np.clip(np.asarray(fallback),m,1-m); _,bm=feasible(backup)
    return backup,True,False,float(bm)
def flags(method):
    return (method not in ("FedRL","RobustAgg","AEFC-no-PATBU"),
            method not in ("FedRL","RobustAgg","AEFC-no-Gate"),
            method not in ("FedRL","RobustAgg","AEFC-no-TGOPA"),
            method not in ("FedRL","RobustAgg","AEFC-no-Shield"),
            method!="FedRL")

def run_episode(seed,method,scenario,outdir,c,cfg_hash):
    tape=make_tape(seed,c); plant=HydroPlant(c); x=plant.reset()
    theta=np.asarray(c.theta_initial,float); anchor=np.asarray(c.theta_anchor,float)
    shadow=theta.copy(); belief=norm_state(x,c); shadow_belief=belief.copy()
    integral=np.zeros(2); shadow_integral=np.zeros(2); backup_integral=np.zeros(2)
    hist=[]; patbu,gate,tgopa,shield,robust=flags(method)
    if method in ("FedRL","RobustAgg"): patbu=gate=tgopa=shield=False
    max_b=max_drift=max_shadow=0.0; violations=sat=shield_n=shield_bad=rejects=accepted=0
    flow=[]; head=[]; speed=[]; power=[]; exec_l2=[]; margins=[]; post_errors=[]
    outdir.mkdir(parents=True,exist_ok=True)
    raw=outdir/f"seed_{seed}.jsonl"
    with raw.open("w",encoding="utf-8") as fp:
      for t in range(c.steps):
        ztrue=norm_state(x,c); zclean=ztrue+tape["sensor"][t]; hist.append(zclean.copy())
        physical=scenario in ("physical","joint"); knowledge=scenario in ("knowledge","joint")
        obs=obs_attack(zclean,t,hist,seed,c) if physical else zclean.copy()
        reports,ages=client_reports(ztrue,t,tape,scenario,c)
        updates=[]
        for j in range(c.clients):
            g=local_gradient(theta,reports[j],integral,c)+tape["update"][t,j]
            if knowledge and attack_active(t,c) and j==c.clients-1:
                g=c.byzantine_gradient_scale*g+np.asarray(c.byzantine_gradient_bias)
            updates.append(g)
        updates=np.asarray(updates); agg=trimmed_mean(updates,c.byzantine) if robust else updates.mean(axis=0)
        if patbu:
            med=np.median(reports,axis=0); residual=np.linalg.norm(reports-med[None,:],axis=1)
            weights=np.exp(-c.patbu_age_decay*ages)/(1+(residual/c.patbu_residual_scale)**2)
            weighted=np.average(reports,axis=0,weights=np.maximum(weights,1e-6))
            belief=np.clip(c.patbu_prior_weight*belief+c.patbu_observation_weight*obs+c.patbu_evidence_weight*weighted,-4,4)
            trust=float(np.clip(weights.mean(),0,1))
        else: belief=obs.copy(); trust=0.95
        berr=float(np.linalg.norm(belief-ztrue)); max_b=max(max_b,berr)
        _,e=controller(belief,theta,integral,c); integral=np.clip(integral+c.dt*e,-0.25,0.25)
        proposed,_=controller(belief,theta,integral,c); xhat=denorm_state(belief,c)
        pred=predict_next(xhat,proposed,c.qin_nominal,c.load_nominal,c,np.zeros(2))
        med=np.median(reports,axis=0)
        disagree=float(np.linalg.norm(obs-med)/math.sqrt(6))
        spread=float(np.median(np.linalg.norm(reports-med[None,:],axis=1)))
        risk=float(max(0.0,np.max(np.maximum(np.asarray(c.state_lower)-pred,pred-np.asarray(c.state_upper))))+
                    c.gate_disagreement_weight*min(disagree,2)+c.gate_spread_weight*min(spread,2))
        _,be=controller(zclean,anchor,backup_integral,c); backup_integral=np.clip(backup_integral+c.dt*be,-0.25,0.25)
        backup,_=controller(zclean,anchor,backup_integral,c)
        allowed=(risk<=c.risk_max and trust>=c.q_min) if gate else True
        if not allowed: rejects+=1; proposed=backup.copy()
        delta=-c.eta*trust*agg
        if tgopa:
            dn=np.linalg.norm(delta)
            if dn>c.clip_norm: delta*=c.clip_norm/max(dn,1e-12)
            dn=np.linalg.norm(delta)
            if dn>c.trust_region: delta*=c.trust_region/max(dn,1e-12)
            cand=theta+delta
            before=np.linalg.norm(theta-np.asarray(c.theta_reference))**2
            after=np.linalg.norm(cand-np.asarray(c.theta_reference))**2
            accept=(trust>=c.q_min and after<=before+c.validation_slack and np.linalg.norm(cand-anchor)<=0.20)
            if accept: theta=cand; accepted+=1
        else: theta=theta+delta; accepted+=1
        max_drift=max(max_drift,float(np.linalg.norm(theta-anchor)))
        clean_reports=ztrue[None,:]+tape["client"][t]
        clean_updates=np.asarray([local_gradient(shadow,clean_reports[j],shadow_integral,c)+tape["update"][t,j] for j in range(c.clients)])
        shadow_agg=trimmed_mean(clean_updates,c.byzantine) if robust else clean_updates.mean(axis=0)
        if patbu:
            shadow_belief=c.patbu_prior_weight*shadow_belief+c.patbu_observation_weight*zclean+c.patbu_evidence_weight*clean_reports.mean(axis=0)
            shadow_trust=1.0
        else: shadow_belief=zclean.copy(); shadow_trust=0.95
        _,se=controller(shadow_belief,shadow,shadow_integral,c)
        shadow_integral=np.clip(shadow_integral+c.dt*se,-0.25,0.25)
        sd=-c.eta*shadow_trust*shadow_agg
        if tgopa:
            dn=np.linalg.norm(sd)
            if dn>c.clip_norm: sd*=c.clip_norm/max(dn,1e-12)
            dn=np.linalg.norm(sd)
            if dn>c.trust_region: sd*=c.trust_region/max(dn,1e-12)
            cs=shadow+sd; bs=np.linalg.norm(shadow-np.asarray(c.theta_reference))**2; as_=np.linalg.norm(cs-np.asarray(c.theta_reference))**2
            if shadow_trust>=c.q_min and as_<=bs+c.validation_slack and np.linalg.norm(cs-anchor)<=0.20: shadow=cs
        else: shadow=shadow+sd
        sherr=float(np.linalg.norm(theta-shadow)); max_shadow=max(max_shadow,sherr)
        if shield:
            xshield=denorm_state(zclean,c)
            u,intervened,feasible,margin=robust_shield(xshield,proposed,backup,c)
            shield_n+=int(intervened); shield_bad+=int(not feasible); margins.append(margin)
            if not feasible: u=backup.copy()
        else: u=np.clip(proposed,0,1); intervened=False; feasible=True; margin=float("nan")
        post=c.command_attack_bound*tape["cmd_sign"][t] if physical and attack_active(t,c) else np.zeros(2)
        x=plant.step(u,tape["qin"][t],tape["load"][t],post)
        violations+=int(not safe_state(x,c)); saturated=bool(np.any(u+post<0) or np.any(u+post>1)); sat+=int(saturated)
        ue=np.clip(u+post,0,1); ex=float(np.linalg.norm(ue-u)); exec_l2.append(ex)
        flow.extend([abs(x[1]-c.q_ref[0]),abs(x[2]-c.q_ref[1])]); head.append(abs(x[0]-1)); speed.append(abs(x[3]-1))
        power.append(abs(plant.power()-c.load_nominal))
        if t>c.attack_end: post_errors.append(sherr)
        row={"seed":seed,"method":method,"scenario":scenario,"t":t,"time_s":round(t*c.dt,8),
             "state_true":x.tolist(),"state_observed":obs.tolist(),"belief":belief.tolist(),"belief_error":berr,
             "theta_deployed":theta.tolist(),"theta_clean_shadow":shadow.tolist(),"theta_shadow_error":sherr,
             "aggregate":agg.tolist(),"trust":trust,"risk_score":risk,"gate_allowed":bool(allowed),
             "theta_update_accepted":bool(accept) if tgopa else True,"valve_command":u.tolist(),
             "valve_executed":ue.tolist(),"post_shield_attack":post.tolist(),"shield_intervened":bool(intervened),
             "shield_feasible":bool(feasible),"actuator_saturated":saturated,
             "shield_margin":margin if np.isfinite(margin) else None,"state_safe":safe_state(x,c),
             "power_output":plant.power(),"attack_active":attack_active(t,c)}
        fp.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
    first=float(post_errors[0]) if post_errors else None; last=float(post_errors[-1]) if post_errors else None
    corr=None; exposed=bool(first is not None and first>c.epsilon)
    for k in range(max(0,len(post_errors)-c.hold_points+1)):
        if post_errors[k]>c.epsilon and np.all(np.asarray(post_errors[k+1:k+1+c.hold_points])<=c.epsilon):
            corr=c.attack_end+1+k+1; break
    summary={"seed":seed,"method":method,"scenario":scenario,"steps":c.steps,"samples":c.steps,
      "flow_mae":float(np.mean(flow)),"head_mae":float(np.mean(head)),"speed_mae":float(np.mean(speed)),
      "power_mae":float(np.mean(power)),"state_violation_points":violations,"actuator_saturation_points":sat,
      "shield_intervention_points":shield_n,"shield_infeasible_points":shield_bad,"gate_reject_points":rejects,
      "accepted_updates":accepted,"max_belief_error":max_b,"max_theta_drift_from_anchor":max_drift,
      "max_dynamic_shadow_error":max_shadow,"post_attack_initial_shadow_error":first,
      "post_attack_final_shadow_error":last,"post_attack_exposed":exposed,"epsilon":c.epsilon,
      "hold_points":c.hold_points,"dynamic_shadow_correction":corr is not None,"first_correction_step":corr,
      "mean_execution_l2":float(np.mean(exec_l2)),"mean_shield_margin":float(np.mean(margins)) if margins else None,
      "model_status":"normalized_uncalibrated_software_in_the_loop","physical_hardware_operated":False,
      "config_sha256":cfg_hash}
    (outdir/f"seed_{seed}.summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return summary

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="configs/hydro_valve_cps_sil_20261030.json")
    ap.add_argument("--output",default="results/hydro_valve_cps_sil_20261030")
    ap.add_argument("--seed-start",type=int,default=None); ap.add_argument("--seeds",type=int,default=None); ap.add_argument("--steps",type=int,default=None)
    args=ap.parse_args(); values=asdict(Config()); cp=Path(args.config)
    if cp.exists(): values.update(json.loads(cp.read_text(encoding="utf-8")))
    for k in ("q_ref","q_coeff","observation_scales","state_lower","state_upper","shield_reserve",
              "physical_observation_bias","byzantine_evidence_bias","byzantine_gradient_bias",
              "theta_initial","theta_anchor","theta_reference"):
        values[k]=tuple(values[k])
    if args.seed_start is not None: values["seed_start"]=args.seed_start
    if args.seeds is not None: values["seeds"]=args.seeds
    if args.steps is not None: values["steps"]=args.steps
    c=Config(**values); cfg_text=json.dumps(asdict(c),sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    cfg_hash=hashlib.sha256(cfg_text.encode()).hexdigest(); root=Path(args.output); root.mkdir(parents=True,exist_ok=True)
    (root/"frozen_config.json").write_text(cfg_text,encoding="utf-8")
    allrows=[]
    for sc in SCENARIOS:
      for method in METHODS:
       for seed in range(c.seed_start,c.seed_start+c.seeds):
        allrows.append(run_episode(seed,method,sc,root/sc/method,c,cfg_hash))
    with (root/"summary.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    manifest={"experiment":"AEFC hydroelectric valve-flow CPS SIL","model_status":"normalized_uncalibrated_software_in_the_loop",
      "physical_hardware_operated":False,"seed_start":c.seed_start,"seed_ids":list(range(c.seed_start,c.seed_start+c.seeds)),
      "seeds":c.seeds,"steps_per_episode":c.steps,"dt_s":c.dt,"scenarios":list(SCENARIOS),"primary_scenarios":list(SCENARIOS),
      "auxiliary_scenarios":[],"methods":list(METHODS),"clients":c.clients,"byzantine_clients":c.byzantine,
      "physical_subsystems":2,"actuators":{"AC1":"valve-opening flow regulator for branch 1","AC2":"valve-opening flow regulator for branch 2"},
      "episodes":len(allrows),"samples":len(allrows)*c.steps,"attack_window_inclusive":[c.attack_start,c.attack_end],
      "correction_criterion":{"epsilon":c.epsilon,"consecutive_points":c.hold_points,"must_start_outside":True},
      "config_sha256":cfg_hash,"summary_rows":len(allrows),
      "interpretation":"SIL evidence only; no physical PLC/actuator I/O; not G1/G3/G5 formal certification"}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    cols=["scenario","method","episodes","mean_flow_mae","mean_head_mae","mean_speed_mae","mean_power_mae",
      "violation_episodes","violation_points","mean_max_belief_error","mean_max_shadow_error","correction_episodes",
      "mean_execution_l2","mean_shield_interventions","mean_gate_rejects","mean_accepted_updates"]
    with (root/"aggregate_by_method_scenario.csv").open("w",newline="",encoding="utf-8") as f:
      w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
      for sc in SCENARIOS:
       for m in METHODS:
        rr=[r for r in allrows if r["scenario"]==sc and r["method"]==m]
        w.writerow({"scenario":sc,"method":m,"episodes":len(rr),"mean_flow_mae":np.mean([r["flow_mae"] for r in rr]),
          "mean_head_mae":np.mean([r["head_mae"] for r in rr]),"mean_speed_mae":np.mean([r["speed_mae"] for r in rr]),
          "mean_power_mae":np.mean([r["power_mae"] for r in rr]),"violation_episodes":sum(r["state_violation_points"]>0 for r in rr),
          "violation_points":sum(r["state_violation_points"] for r in rr),"mean_max_belief_error":np.mean([r["max_belief_error"] for r in rr]),
          "mean_max_shadow_error":np.mean([r["max_dynamic_shadow_error"] for r in rr]),
          "correction_episodes":sum(r["dynamic_shadow_correction"] for r in rr),
          "mean_execution_l2":np.mean([r["mean_execution_l2"] for r in rr]),
          "mean_shield_interventions":np.mean([r["shield_intervention_points"] for r in rr]),
          "mean_gate_rejects":np.mean([r["gate_reject_points"] for r in rr]),
          "mean_accepted_updates":np.mean([r["accepted_updates"] for r in rr])})
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
