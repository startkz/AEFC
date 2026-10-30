#!/usr/bin/env python3
"""AEFC hydroelectric valve-flow CPS software-in-the-loop experiment.

This is a normalized, uncalibrated SIL model of the documented four-layer
MH1/MH2-HMI/ES-S7-300/S7-1500-AC1/AC2 architecture. It does NOT connect to or
operate physical PLCs or actuators. AC1/AC2 are modeled as valve-opening
flow-regulation actuators.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

SCENARIOS = ("clean", "physical", "knowledge", "joint")
METHODS = ("FedRL", "RobustAgg", "AEFC-no-PATBU", "AEFC-no-Gate",
           "AEFC-no-TGOPA", "AEFC-no-Shield", "AEFC-Full")

@dataclass(frozen=True)
class Config:
    steps: int = 480
    seed_start: int = 220
    seeds: int = 20
    dt: float = 0.05
    attack_start: int = 120
    attack_end: int = 239
    clients: int = 5
    byzantine: int = 1
    q_ref: Tuple[float, float] = (0.48, 0.42)
    q_coeff: Tuple[float, float] = (0.58, 0.52)
    q_tau: float = 0.35
    valve_tau: float = 0.25
    valve_rate: float = 0.70
    reservoir_area: float = 15.0
    turbine_eta: float = 0.92
    turbine_inertia: float = 0.65
    turbine_damping: float = 0.45
    qin_nominal: float = 0.90
    load_nominal: float = 0.92 * 0.90
    observation_scales: Tuple[float, ...] = (0.08, 0.10, 0.10, 0.03, 0.25, 0.25)
    state_lower: Tuple[float, ...] = (0.92, 0.38, 0.33, 0.97, 0.0, 0.0)
    state_upper: Tuple[float, ...] = (1.08, 0.58, 0.51, 1.03, 1.0, 1.0)
    shield_reserve: Tuple[float, ...] = (0.005, 0.015, 0.015, 0.005, 0.02, 0.02)
    command_attack_bound: float = 0.080
    proposal_tamper_bound: float = 0.22
    qin_uncertainty: float = 0.004
    load_uncertainty: float = 0.006
    sensor_noise_bound: float = 0.010
    client_noise_bound: float = 0.018
    update_noise_bound: float = 0.004
    physical_observation_bias: Tuple[float, ...] = (0.28, 0.42, -0.38, 0.24, -0.18, 0.18)
    replay_delay: int = 4
    replay_weight: float = 0.65
    byzantine_evidence_bias: Tuple[float, ...] = (1.4, -1.1, 1.0, -0.8, 0.9, -0.9)
    byzantine_gradient_scale: float = 3.5
    byzantine_gradient_bias: Tuple[float, ...] = (0.20, -0.10, -0.18, 0.09)
    patbu_prior_weight: float = 0.20
    patbu_observation_weight: float = 0.15
    patbu_evidence_weight: float = 0.65
    patbu_age_decay: float = 0.15
    patbu_residual_scale: float = 0.45
    gate_disagreement_weight: float = 0.025
    gate_spread_weight: float = 0.010
    eta: float = 0.010
    clip_norm: float = 0.020
    trust_region: float = 0.005
    q_min: float = 0.90
    risk_max: float = 0.004
    validation_slack: float = 1e-7
    belief_lambda: float = 0.20
    evidence_scale: float = 0.55
    proximal_lambda: float = 0.002
    theta_initial: Tuple[float, ...] = (0.90, 0.055, 0.90, 0.055)
    theta_anchor: Tuple[float, ...] = (0.90, 0.055, 0.90, 0.055)
    theta_reference: Tuple[float, ...] = (0.92, 0.060, 0.88, 0.055)
    epsilon: float = 0.001
    hold_points: int = 20

CFG = Config()

class HydroPlant:
    """Reduced-order coupled reservoir/penstock/turbine/valve process."""
    def __init__(self, cfg: Config):
        self.c = cfg
        self.x = np.array([1.0, 0.46, 0.40, 0.995,
                           0.46/cfg.q_coeff[0], 0.40/cfg.q_coeff[1]], dtype=float)

    def reset(self, initial: np.ndarray | None = None):
        if initial is not None:
            self.x = np.array(initial, dtype=float).copy()
        else:
            self.x = np.array([1.0, 0.46, 0.40, 0.995,
                               0.46/self.c.q_coeff[0], 0.40/self.c.q_coeff[1]], dtype=float)
        return self.x.copy()

    def step(self, command: np.ndarray, qin: float, load: float,
             post_attack: np.ndarray | None = None) -> np.ndarray:
        c = self.c; dt = c.dt
        post = np.zeros(2) if post_attack is None else np.asarray(post_attack, dtype=float)
        executed = np.asarray(command, dtype=float) + post
        executed = np.clip(executed, 0.0, 1.0)
        h, q1, q2, omega, a1, a2 = self.x
        alpha = np.array([a1, a2])
        rate = np.clip((executed-alpha)/c.valve_tau, -c.valve_rate, c.valve_rate)
        alpha_new = np.clip(alpha + dt*rate, 0.0, 1.0)
        qs = np.array(c.q_coeff) * alpha_new * math.sqrt(max(h, 0.2))
        q_new = np.array([q1, q2]) + dt/c.q_tau*(qs-np.array([q1,q2]))
        q_new = np.maximum(q_new, 0.0)
        h_new = h + dt*(qin-float(q_new.sum()))/c.reservoir_area
        p_mech = c.turbine_eta*h_new*float(q_new.sum())
        omega_new = omega + dt/c.turbine_inertia*(p_mech-load-c.turbine_damping*(omega-1.0))
        self.x = np.array([h_new, q_new[0], q_new[1], omega_new, alpha_new[0], alpha_new[1]])
        return self.x.copy()

    def output_power(self) -> float:
        return self.c.turbine_eta*self.x[0]*(self.x[1]+self.x[2])


def norm_state(x: np.ndarray, c: Config) -> np.ndarray:
    base = np.array([1.0, c.q_ref[0], c.q_ref[1], 1.0,
                     c.q_ref[0]/c.q_coeff[0], c.q_ref[1]/c.q_coeff[1]])
    return (np.asarray(x)-base)/np.array(c.observation_scales)

def denorm_state(z: np.ndarray, c: Config) -> np.ndarray:
    base = np.array([1.0, c.q_ref[0], c.q_ref[1], 1.0,
                     c.q_ref[0]/c.q_coeff[0], c.q_ref[1]/c.q_coeff[1]])
    return base + np.asarray(z)*np.array(c.observation_scales)

def safe_state(x: np.ndarray, c: Config) -> bool:
    return bool(np.all(x >= np.array(c.state_lower)-1e-12) and np.all(x <= np.array(c.state_upper)+1e-12))

def make_tape(seed: int, c: Config) -> Dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.arange(c.steps)
    qin = c.qin_nominal + 0.0025*np.sin(0.031*t+seed*0.13) + rng.normal(0,0.0008,c.steps)
    load = c.load_nominal + 0.0040*np.sin(0.023*t+seed*0.07+0.4) + rng.normal(0,0.0010,c.steps)
    sensor = rng.uniform(-c.sensor_noise_bound, c.sensor_noise_bound, (c.steps,6))
    client = rng.uniform(-c.client_noise_bound, c.client_noise_bound, (c.steps,c.clients,6))
    update = rng.uniform(-c.update_noise_bound, c.update_noise_bound, (c.steps,c.clients,4))
    cmd_sign = rng.choice(np.array([-1.0,1.0]), size=(c.steps,2))
    return {"qin":qin,"load":load,"sensor":sensor,"client":client,"update":update,"cmd_sign":cmd_sign}

def attack_active(t: int, c: Config) -> bool:
    return c.attack_start <= t <= c.attack_end

def physical_obs_attack(z: np.ndarray, t: int, history: List[np.ndarray], seed: int, c: Config) -> np.ndarray:
    if not attack_active(t,c): return z.copy()
    sign = -1.0 if seed % 2 else 1.0
    bias = sign*np.array(c.physical_observation_bias)
    if t < c.attack_start+60:
        return z+bias
    idx=max(0,t-c.replay_delay)
    replay=history[idx] if idx < len(history) else z
    return c.replay_weight*replay+(1.0-c.replay_weight)*z+bias*0.25

def client_evidence(z: np.ndarray, t: int, tape: Dict[str,np.ndarray], scenario: str, c: Config) -> Tuple[np.ndarray,np.ndarray]:
    reports = z[None,:] + tape["client"][t]
    ages = np.zeros(c.clients,dtype=float)
    if scenario in ("knowledge","joint") and attack_active(t,c):
        j=c.clients-1
        reports[j] = reports[j] + np.array(c.byzantine_evidence_bias)
        ages[j]=4.0
    return reports,ages

def trimmed_mean(values: np.ndarray, f: int) -> np.ndarray:
    arr=np.sort(np.asarray(values),axis=0)
    if arr.shape[0] <= 2*f: raise ValueError("n_valid must be greater than 2f")
    return np.mean(arr[f:arr.shape[0]-f],axis=0) if f else np.mean(arr,axis=0)

def local_gradient(theta: np.ndarray, report: np.ndarray, integral: np.ndarray, c: Config) -> np.ndarray:
    """Analytic gradient of a one-step valve-flow tracking loss."""
    xhat=denorm_state(report,c)
    h,q1,q2,omega,a1,a2=xhat
    e=np.array([c.q_ref[0]-q1+0.08*(1.0-h)+0.03*(1.0-omega),
                c.q_ref[1]-q2+0.08*(1.0-h)+0.03*(1.0-omega)])
    base=np.array([c.q_ref[0]/c.q_coeff[0],c.q_ref[1]/c.q_coeff[1]])
    u=np.array([base[0]+theta[0]*e[0]+theta[1]*integral[0],
                base[1]+theta[2]*e[1]+theta[3]*integral[1]])
    u=np.clip(u,0,1)
    alpha=np.array([a1,a2])
    raw_rate=(u-alpha)/c.valve_tau
    rate=np.clip(raw_rate,-c.valve_rate,c.valve_rate)
    alpha_next=np.clip(alpha+c.dt*rate,0,1)
    q_now=np.array([q1,q2])
    q_next=q_now+c.dt/c.q_tau*(np.array(c.q_coeff)*alpha_next*math.sqrt(max(h,0.2))-q_now)
    grad=np.zeros(4)
    for i,(kp_idx,ki_idx) in enumerate(((0,1),(2,3))):
        # Derivatives are zero when the actuator rate or opening saturates.
        active=(abs(raw_rate[i])<c.valve_rate and 0.0<alpha_next[i]<1.0)
        if active:
            dq_dalpha=c.dt/c.q_tau*c.q_coeff[i]*math.sqrt(max(h,0.2))
            dalpha_dkp=c.dt/c.valve_tau*e[i]
            dalpha_dki=c.dt/c.valve_tau*integral[i]
            grad[kp_idx]=(q_next[i]-c.q_ref[i])*dq_dalpha*dalpha_dkp
            grad[ki_idx]=(q_next[i]-c.q_ref[i])*dq_dalpha*dalpha_dki
    grad += 2e-4*(theta-np.array(c.theta_reference))
    return grad

def controller_command(belief: np.ndarray, theta: np.ndarray, integral: np.ndarray, c: Config) -> Tuple[np.ndarray,np.ndarray]:
    xhat=denorm_state(belief,c)
    h,q1,q2,omega,a1,a2=xhat
    e=np.array([c.q_ref[0]-q1+0.08*(1.0-h)+0.03*(1.0-omega),
                c.q_ref[1]-q2+0.08*(1.0-h)+0.03*(1.0-omega)])
    base=np.array([c.q_ref[0]/c.q_coeff[0],c.q_ref[1]/c.q_coeff[1]])
    u=np.array([base[0]+theta[0]*e[0]+theta[1]*integral[0],
                base[1]+theta[2]*e[1]+theta[3]*integral[1]])
    return np.clip(u,0,1),e

def predict_next(x: np.ndarray, u: np.ndarray, qin: float, load: float, c: Config, post: np.ndarray) -> np.ndarray:
    # Side-effect-free copy of plant step for robust one-step screening.
    h,q1,q2,w,a1,a2=np.asarray(x,dtype=float)
    ue=np.clip(np.asarray(u)+np.asarray(post),0,1)
    a=np.array([a1,a2]); rate=np.clip((ue-a)/c.valve_tau,-c.valve_rate,c.valve_rate)
    an=np.clip(a+c.dt*rate,0,1)
    qss=np.array(c.q_coeff)*an*math.sqrt(max(h,0.2))
    qn=np.maximum(np.array([q1,q2])+c.dt/c.q_tau*(qss-np.array([q1,q2])),0)
    hn=h+c.dt*(qin-float(qn.sum()))/c.reservoir_area
    pm=c.turbine_eta*hn*float(qn.sum())
    wn=w+c.dt/c.turbine_inertia*(pm-load-c.turbine_damping*(w-1))
    return np.array([hn,qn[0],qn[1],wn,an[0],an[1]])

def trusted_candidate_loss(theta: np.ndarray, xloc: np.ndarray, integral: np.ndarray, c: Config) -> float:
    """PLC-local measured-state, model-proxy one-step *candidate-dependent* check.

    Uses no clean theta, attacker label, true physical state, or offline shadow.
    The trusted measurement and reduced-order predictor are assumed, and this
    does NOT independently establish generalization or G2/G5 certification.
    """
    local_z=norm_state(xloc,c)
    proposed,_=controller_command(local_z,theta,integral,c)
    future=predict_next(xloc,proposed,c.qin_nominal,c.load_nominal,c,np.zeros(2))
    if not np.all(np.isfinite(future)):
        return float("inf")
    return float(np.mean((future[1:3]-np.asarray(c.q_ref))**2))

def robust_shield(xhat: np.ndarray, proposed: np.ndarray, fallback: np.ndarray, c: Config) -> Tuple[np.ndarray,bool,bool,float]:
    lo=np.array(c.state_lower)+np.array(c.shield_reserve)
    hi=np.array(c.state_upper)-np.array(c.shield_reserve)
    margin=c.command_attack_bound
    safe_lo=np.full(2,margin); safe_hi=np.full(2,1.0-margin)
    target=np.clip(np.asarray(proposed,dtype=float),safe_lo,safe_hi)
    corners=[np.array([a,b]) for a in (-margin,margin) for b in (-margin,margin)]
    def feasible(u):
        margins=[]
        for post in corners:
            xn=predict_next(xhat,u,c.qin_nominal-c.qin_uncertainty,
                            c.load_nominal+c.load_uncertainty,c,post)
            margins.extend((xn-lo).tolist()); margins.extend((hi-xn).tolist())
        return min(margins)>=-1e-10, min(margins)
    ok,mar=feasible(target)
    if ok:
        return target,bool(np.linalg.norm(target-np.asarray(proposed))>1e-10),True,float(mar)
    # Search the bounded valve-command domain for the feasible point closest to the proposal.
    grid=np.linspace(margin,1.0-margin,13)
    best=None; best_dist=float("inf"); best_margin=float("-inf")
    for u1 in grid:
        for u2 in grid:
            candidate=np.array([u1,u2])
            ok,cm=feasible(candidate)
            if ok:
                dist=float(np.linalg.norm(candidate-np.asarray(proposed)))
                if dist<best_dist:
                    best=candidate; best_dist=dist; best_margin=float(cm)
    if best is not None:
        return best,True,True,best_margin
    backup=np.clip(np.asarray(fallback,dtype=float),safe_lo,safe_hi)
    _,backup_margin=feasible(backup)
    return backup,True,False,float(backup_margin)

def method_flags(method: str):
    return (
        method not in ("FedRL", "RobustAgg", "AEFC-no-PATBU"),
        method not in ("FedRL", "RobustAgg", "AEFC-no-Gate"),
        method not in ("FedRL", "RobustAgg", "AEFC-no-TGOPA"),
        method not in ("FedRL", "RobustAgg", "AEFC-no-Shield"),
        method != "FedRL",
    )

def run_episode(seed: int, method: str, scenario: str, out_dir: Path, c: Config, cfg_hash: str) -> Dict:
    tape=make_tape(seed,c); plant=HydroPlant(c); x=plant.reset()
    theta=np.array(c.theta_initial,dtype=float); anchor=np.array(c.theta_anchor,dtype=float)
    theta_shadow=theta.copy(); belief=norm_state(x,c); shadow_belief=belief.copy()
    integral=np.zeros(2); shadow_integral=np.zeros(2); backup_integral=np.zeros(2)
    last_safe_cmd=x[4:6].copy()
    obs_history=[]; rows=[]
    patbu,gate,tgopa,shield,robust=method_flags(method)
    if method in ("FedRL","RobustAgg"): patbu=False; gate=False; tgopa=False; shield=False
    max_belief=0.0; max_theta_shadow=0.0; max_theta_drift=0.0
    violations=0; actuator_sat=0; shield_steps=0; shield_infeasible=0; gate_rejects=0; accepted=0
    flow_abs=[]; head_abs=[]; speed_abs=[]; power_abs=[]; exec_l2=[]; margins=[]
    correction_first=None; post_attack_error=[]; theta_shadow_errors=[]
    out_dir.mkdir(parents=True,exist_ok=True)
    raw_path=out_dir/f"seed_{seed}.jsonl"
    with raw_path.open("w",encoding="utf-8") as fp:
        for t in range(c.steps):
            z_true=norm_state(x,c)
            z_clean=z_true+tape["sensor"][t]
            obs_history.append(z_clean.copy())
            physical=scenario in ("physical","joint")
            knowledge=scenario in ("knowledge","joint")
            proposal_tamper=(scenario=="post_gate_command_tamper")
            obs=physical_obs_attack(z_clean,t,obs_history,seed,c) if physical else z_clean.copy()
            reports,ages=client_evidence(z_true,t,tape,scenario,c)
            # Each client update is computed from its local report; only one client is Byzantine.
            updates=[]
            for j in range(c.clients):
                g=local_gradient(theta,reports[j],integral,c)+tape["update"][t,j]
                if knowledge and attack_active(t,c) and j==c.clients-1:
                    g=c.byzantine_gradient_scale*g+np.array(c.byzantine_gradient_bias)
                updates.append(g)
            updates=np.asarray(updates)
            if robust:
                agg=trimmed_mean(updates,c.byzantine)
            else:
                agg=np.mean(updates,axis=0)
            # PATBU uses receiver-side freshness and robust consistency; no ground-truth attacker ID is read.
            if patbu:
                med=np.median(reports,axis=0)
                residual=np.linalg.norm(reports-med[None,:],axis=1)
                weights=np.exp(-c.patbu_age_decay*ages)/(1.0+(residual/c.patbu_residual_scale)**2)
                weighted=np.average(reports,axis=0,weights=np.maximum(weights,1e-6))
                knowledge_belief=c.patbu_prior_weight*belief+c.patbu_observation_weight*obs+c.patbu_evidence_weight*weighted
                belief=np.clip(knowledge_belief,-4.0,4.0)
                trust=float(np.clip(np.mean(weights),0.0,1.0))
            else:
                belief=obs.copy(); trust=0.95
            belief_error=float(np.linalg.norm(belief-z_true))
            max_belief=max(max_belief,belief_error)
            # Flow tracking errors and integral state are estimated from the current belief.
            _,e=controller_command(belief,theta,integral,c)
            integral=np.clip(integral+c.dt*e,-0.25,0.25)
            proposed,_=controller_command(belief,theta,integral,c)
            xhat=denorm_state(belief,c)
            # Independent PLC-local backup controller; it does not consume federated belief or candidate parameters.
            _,backup_e=controller_command(z_clean,anchor,backup_integral,c)
            backup_integral=np.clip(backup_integral+c.dt*backup_e,-0.25,0.25)
            backup_cmd,_=controller_command(z_clean,anchor,backup_integral,c)
            pred=predict_next(xhat,proposed,c.qin_nominal,c.load_nominal,c,np.zeros(2))
            median_report=np.median(reports,axis=0)
            disagreement=float(np.linalg.norm(obs-median_report)/math.sqrt(6.0))
            report_spread=float(np.median(np.linalg.norm(reports-median_report[None,:],axis=1)))
            risk=float(max(0.0,np.max(np.maximum(np.array(c.state_lower)-pred,pred-np.array(c.state_upper)))) +
                       c.gate_disagreement_weight*min(disagreement,2.0)+c.gate_spread_weight*min(report_spread,2.0))
            allowed=(risk<=c.risk_max and trust>=c.q_min) if gate else True
            if not allowed:
                gate_rejects+=1
                proposed=backup_cmd.copy()
            # Auxiliary interface stress: command is modified after the gate but before the final shield.
            if proposal_tamper and attack_active(t,c):
                proposed=np.clip(proposed+c.proposal_tamper_bound*tape["cmd_sign"][t],0.0,1.0)
            # TGOPA: clipping, trust-region projection, receiver-side acceptance check.
            delta=-c.eta*trust*agg
            if tgopa:
                dn=np.linalg.norm(delta)
                if dn>c.clip_norm: delta*=c.clip_norm/max(dn,1e-12)
                dn=np.linalg.norm(delta)
                if dn>c.trust_region: delta*=c.trust_region/max(dn,1e-12)
                candidate=theta+delta
                # Receiver-side proxy validation on *PLC-local telemetry*.
                # Does not read a privileged clean policy or reference parameter.
                # This is a one-step model-proxy acceptance test, NOT an
                # independent held-out experiment or verified deployment proof.
                xloc=denorm_state(z_clean,c)
                before=trusted_candidate_loss(theta,xloc,integral,c)
                after=trusted_candidate_loss(candidate,xloc,integral,c)
                accept=(trust>=c.q_min and np.isfinite(after) and
                        after<=before+c.validation_slack and np.linalg.norm(candidate-anchor)<=0.20)
                if accept: theta=candidate; accepted+=1
            else:
                theta=theta+delta; accepted+=1
            max_theta_drift=max(max_theta_drift,float(np.linalg.norm(theta-anchor)))
            # The offline clean shadow follows the same method-specific update operator on the same true plant trajectory.
            clean_reports=z_true[None,:]+tape["client"][t]
            clean_updates=np.asarray([local_gradient(theta_shadow,clean_reports[j],shadow_integral,c)+tape["update"][t,j]
                                      for j in range(c.clients)])
            shadow_agg=trimmed_mean(clean_updates,c.byzantine) if robust else np.mean(clean_updates,axis=0)
            if patbu:
                shadow_belief=c.patbu_prior_weight*shadow_belief+c.patbu_observation_weight*z_clean+c.patbu_evidence_weight*np.mean(clean_reports,axis=0)
                shadow_trust=1.0
            else:
                shadow_belief=z_clean.copy(); shadow_trust=0.95
            _,se=controller_command(shadow_belief,theta_shadow,shadow_integral,c)
            shadow_integral=np.clip(shadow_integral+c.dt*se,-0.25,0.25)
            sdelta=-c.eta*shadow_trust*shadow_agg
            if tgopa:
                sn=np.linalg.norm(sdelta)
                if sn>c.clip_norm: sdelta*=c.clip_norm/max(sn,1e-12)
                sn=np.linalg.norm(sdelta)
                if sn>c.trust_region: sdelta*=c.trust_region/max(sn,1e-12)
                cand_s=theta_shadow+sdelta
                b_s=trusted_candidate_loss(theta_shadow,denorm_state(z_clean,c),shadow_integral,c)
                a_s=trusted_candidate_loss(cand_s,denorm_state(z_clean,c),shadow_integral,c)
                if shadow_trust>=c.q_min and np.isfinite(a_s) and a_s<=b_s+c.validation_slack and np.linalg.norm(cand_s-anchor)<=0.20:
                    theta_shadow=cand_s
            else:
                theta_shadow=theta_shadow+sdelta
            shadow_error=float(np.linalg.norm(theta-theta_shadow))
            max_theta_shadow=max(max_theta_shadow,shadow_error); theta_shadow_errors.append(shadow_error)
            # Physical execution shield; model predicts the bounded post-shield valve-command attack.
            if shield:
                xhat_shield=denorm_state(z_clean,c)  # bounded-error local PLC telemetry, independent of HMI/ES attack
                u_cmd,intervened,shield_feasible,margin=robust_shield(xhat_shield,proposed,backup_cmd,c)
                shield_steps+=int(intervened); shield_infeasible+=int(not shield_feasible); margins.append(margin)
                if shield_feasible: last_safe_cmd=u_cmd.copy()
                else: u_cmd=backup_cmd.copy()
            else:
                u_cmd=np.clip(proposed,0,1); intervened=False; shield_feasible=True; margin=float("nan")
            if physical and attack_active(t,c):
                post=c.command_attack_bound*tape["cmd_sign"][t]
            else:
                post=np.zeros(2)
            x_prev=x.copy()
            x=plant.step(u_cmd,tape["qin"][t],tape["load"][t],post)
            if not safe_state(x,c): violations+=1
            actuator_sat+=int(np.any((u_cmd+post<0)|(u_cmd+post>1)))
            actual_u=np.clip(u_cmd+post,0,1)
            exec_l2.append(float(np.linalg.norm(actual_u-u_cmd)))
            flow_abs.extend([abs(x[1]-c.q_ref[0]),abs(x[2]-c.q_ref[1])])
            head_abs.append(abs(x[0]-1.0)); speed_abs.append(abs(x[3]-1.0)); power_abs.append(abs(plant.output_power()-c.load_nominal))
            if t>=c.attack_end+1: post_attack_error.append(shadow_error)
            row={"seed":seed,"method":method,"scenario":scenario,"t":t,"time_s":round(t*c.dt,8),
                 "state_true":x.tolist(),"state_observed":obs.tolist(),"belief":belief.tolist(),
                 "belief_error":belief_error,"theta_deployed":theta.tolist(),"theta_clean_shadow":theta_shadow.tolist(),
                 "theta_shadow_error":shadow_error,"aggregate":agg.tolist(),"trust":trust,"risk_score":risk,
                 "gate_allowed":bool(allowed),"theta_update_accepted":bool(accept) if tgopa else True,
                 "valve_command":u_cmd.tolist(),"valve_executed":actual_u.tolist(),"post_shield_attack":post.tolist(),
                 "shield_intervened":bool(intervened),"shield_feasible":bool(shield_feasible),
                 "actuator_saturated":bool(np.any((u_cmd+post<0)|(u_cmd+post>1))),
                 "shield_margin":margin if np.isfinite(margin) else None,"state_safe":safe_state(x,c),
                 "power_output":plant.output_power(),"attack_active":attack_active(t,c)}
            fp.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
    # The strict correction criterion requires a post-attack threshold crossing from outside and 20 consecutive points.
    earr=np.asarray(post_attack_error,dtype=float); start_t=c.attack_end+1
    exposed=bool(len(earr)>0 and earr[0]>c.epsilon)
    for k in range(max(0,len(earr)-c.hold_points)):
        if exposed and earr[k]>c.epsilon and np.all(earr[k+1:k+1+c.hold_points]<=c.epsilon):
            correction_first=start_t+k+1; break
    summary={"seed":seed,"method":method,"scenario":scenario,"steps":c.steps,"samples":c.steps,
        "flow_mae":float(np.mean(flow_abs)),"head_mae":float(np.mean(head_abs)),"speed_mae":float(np.mean(speed_abs)),
        "power_mae":float(np.mean(power_abs)),"state_violation_points":violations,"actuator_saturation_points":actuator_sat,
        "shield_intervention_points":shield_steps,"shield_infeasible_points":shield_infeasible,
        "gate_reject_points":gate_rejects,"accepted_updates":accepted,"max_belief_error":max_belief,
        "max_theta_drift_from_anchor":max_theta_drift,"max_dynamic_shadow_error":max_theta_shadow,
        "post_attack_initial_shadow_error":float(earr[0]) if len(earr) else None,
        "post_attack_final_shadow_error":float(earr[-1]) if len(earr) else None,
        "post_attack_exposed":exposed,"epsilon":c.epsilon,"hold_points":c.hold_points,
        "dynamic_shadow_correction":correction_first is not None,"first_correction_step":correction_first,
        "mean_execution_l2":float(np.mean(exec_l2)),"mean_shield_margin":float(np.nanmean(margins)) if margins else None,
        "model_status":"normalized_uncalibrated_software_in_the_loop","physical_hardware_operated":False,
        "config_sha256":cfg_hash}
    (out_dir/f"seed_{seed}.summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return summary

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="configs/hydro_valve_cps_sil_20261030.json")
    ap.add_argument("--output",default="results/hydro_valve_cps_sil_20261030")
    ap.add_argument("--seed-start",type=int,default=None)
    ap.add_argument("--seeds",type=int,default=None)
    ap.add_argument("--steps",type=int,default=None)
    ap.add_argument("--include-interface-stress",action="store_true",help="Append the exploratory post-gate command-tamper stress; excluded from the preregistered primary matrix.")
    args=ap.parse_args()
    config_path=Path(args.config)
    values=asdict(Config())
    if config_path.exists():
        loaded=json.loads(config_path.read_text(encoding="utf-8"))
        values.update(loaded)
    for key in ("q_ref","q_coeff","observation_scales","state_lower","state_upper",
                "physical_observation_bias","byzantine_evidence_bias","byzantine_gradient_bias","shield_reserve",
                "theta_initial","theta_anchor","theta_reference"):
        if key in values: values[key]=tuple(values[key])
    if args.seed_start is not None: values["seed_start"]=args.seed_start
    if args.seeds is not None: values["seeds"]=args.seeds
    if args.steps is not None: values["steps"]=args.steps
    c=Config(**values)
    config_dict=asdict(c)
    config_text=json.dumps(config_dict,sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    cfg_hash=hashlib.sha256(config_text.encode()).hexdigest()
    root=Path(args.output); root.mkdir(parents=True,exist_ok=True)
    (root/"frozen_config.json").write_text(config_text,encoding="utf-8")
    scenario_list=list(SCENARIOS)+( ["post_gate_command_tamper"] if args.include_interface_stress else [] )
    all_rows=[]
    for scenario in scenario_list:
        for method in METHODS:
            for seed in range(c.seed_start,c.seed_start+c.seeds):
                od=root/scenario/method
                all_rows.append(run_episode(seed,method,scenario,od,c,cfg_hash))
    fields=list(all_rows[0].keys())
    with (root/"summary.csv").open("w",newline="",encoding="utf-8") as fp:
        w=csv.DictWriter(fp,fieldnames=fields); w.writeheader(); w.writerows(all_rows)
    manifest={"experiment":"AEFC hydroelectric valve-flow CPS SIL",
        "model_status":"normalized_uncalibrated_software_in_the_loop",
        "physical_hardware_operated":False,"seed_start":c.seed_start,"seed_ids":list(range(c.seed_start,c.seed_start+c.seeds)),
        "seeds":c.seeds,"steps_per_episode":c.steps,"dt_s":c.dt,
        "scenarios":scenario_list,"primary_scenarios":list(SCENARIOS),
        "auxiliary_scenarios":["post_gate_command_tamper"] if args.include_interface_stress else [],"methods":list(METHODS),"clients":c.clients,"byzantine_clients":c.byzantine,
        "physical_subsystems":2,"actuators":{"AC1":"valve-opening flow regulator for branch 1","AC2":"valve-opening flow regulator for branch 2"},
        "episodes":len(all_rows),"samples":len(all_rows)*c.steps,
        "attack_window_inclusive":[c.attack_start,c.attack_end],
        "correction_criterion":{"epsilon":c.epsilon,"consecutive_points":c.hold_points,"must_start_outside":True},
        "config_sha256":cfg_hash,"summary_rows":len(all_rows),
        "interpretation":"SIL evidence only; no physical PLC/actuator I/O; not G1/G3/G5 formal certification"}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    with (root/"aggregate_by_method_scenario.csv").open("w",newline="",encoding="utf-8") as fp:
        cols=["scenario","method","episodes","mean_flow_mae","mean_head_mae","mean_speed_mae","mean_power_mae",
              "violation_episodes","violation_points","mean_max_belief_error","mean_max_shadow_error","correction_episodes",
              "mean_execution_l2","mean_shield_interventions","mean_gate_rejects","mean_accepted_updates"]
        w=csv.DictWriter(fp,fieldnames=cols); w.writeheader()
        for sc in scenario_list:
            for m in METHODS:
                rr=[r for r in all_rows if r["scenario"]==sc and r["method"]==m]
                w.writerow({"scenario":sc,"method":m,"episodes":len(rr),
                    "mean_flow_mae":np.mean([r["flow_mae"] for r in rr]),"mean_head_mae":np.mean([r["head_mae"] for r in rr]),
                    "mean_speed_mae":np.mean([r["speed_mae"] for r in rr]),"mean_power_mae":np.mean([r["power_mae"] for r in rr]),
                    "violation_episodes":sum(r["state_violation_points"]>0 for r in rr),
                    "violation_points":sum(r["state_violation_points"] for r in rr),
                    "mean_max_belief_error":np.mean([r["max_belief_error"] for r in rr]),
                    "mean_max_shadow_error":np.mean([r["max_dynamic_shadow_error"] for r in rr]),
                    "correction_episodes":sum(r["dynamic_shadow_correction"] for r in rr),
                    "mean_execution_l2":np.mean([r["mean_execution_l2"] for r in rr]),
                    "mean_shield_interventions":np.mean([r["shield_intervention_points"] for r in rr]),
                    "mean_gate_rejects":np.mean([r["gate_reject_points"] for r in rr]),
                    "mean_accepted_updates":np.mean([r["accepted_updates"] for r in rr])})
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=="__main__": main()