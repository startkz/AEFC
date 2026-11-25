#!/usr/bin/env python3
"""TDSC-R1 additional experiment: unprivileged online loop + discrete execution contract.

Imports the *existing* valve-flow SIL plant and analytic parameter update. This
experiment is new evidence, not a regeneration/replacement of the frozen SIL runs.
No claim of real PLC validation, continuous-time CBF invariance, or learned NN-FRL.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from dataclasses import dataclass, replace, asdict
from pathlib import Path
from typing import Optional
import numpy as np

from .run_hydro_valve_cps import (
    Config, HydroPlant, norm_state, denorm_state, make_tape, controller_command,
    local_gradient, predict_next, trusted_candidate_loss, safe_state,
)


@dataclass(frozen=True)
class OnlineInputs:
    """Only information available across the defined online trust boundary."""
    local_plc_norm: np.ndarray
    received_hmi_norm: np.ndarray
    federated_reports: np.ndarray
    received_ages: np.ndarray
    reported_updates: np.ndarray


@dataclass
class OnlineMemory:
    theta: np.ndarray
    belief: np.ndarray
    integral: np.ndarray
    backup_integral: np.ndarray


@dataclass
class Decision:
    command: Optional[np.ndarray]
    status: str
    trust: float
    gate_allowed: bool
    deploy_accepted: bool
    certified_margin: Optional[float]
    work: int


def _clip01(x):
    return np.clip(np.asarray(x, dtype=float), 0.0, 1.0)


def state_uncertainty(local_norm: np.ndarray, c: Config):
    """Trusted sensor interval. Caller may not use simulated plant state."""
    measured = denorm_state(np.asarray(local_norm, dtype=float), c)
    error = c.sensor_noise_bound * np.asarray(c.observation_scales, dtype=float)
    return measured - error, measured + error


def interval_step(lo: np.ndarray, hi: np.ndarray, command: np.ndarray, c: Config):
    """Sound one-step enclosure of HydroPlant.step under declared box bounds.

    Proof: clamp is monotone; actuator/flow bounds use interval arithmetic;
    Euler flow is a positive affine combination because 0<=dt/q_tau<=1;
    product of positive h and flow intervals is monotone; omega update is a
    positive affine combination if 0<=dt*damping/inertia<=1. The resulting
    enclosure includes every command attack in [-bound,bound]^2 and every
    qin/load in their specified boxes, including points between corners.
    This is a *sampled one-step* contract, not a hold-interval safety proof.
    """
    lo = np.asarray(lo, dtype=float); hi = np.asarray(hi, dtype=float)
    u = np.asarray(command, dtype=float)
    if (lo.shape != (6,) or hi.shape != (6,) or u.shape != (2,)
            or not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi)) and np.all(np.isfinite(u)))
            or np.any(lo > hi) or lo[0] <= 0.2 or np.any(lo[1:3] < 0.0)
            or not 0 < c.dt/c.q_tau <= 1
            or not 0 <= c.dt*c.turbine_damping/c.turbine_inertia <= 1):
        raise ValueError('Unsupported or non-finite interval domain')
    a = c.command_attack_bound
    ue_lo = _clip01(u-a); ue_hi = _clip01(u+a)
    rate_lo = np.clip((ue_lo - hi[4:6])/c.valve_tau, -c.valve_rate, c.valve_rate)
    rate_hi = np.clip((ue_hi - lo[4:6])/c.valve_tau, -c.valve_rate, c.valve_rate)
    an_lo = _clip01(lo[4:6] + c.dt*rate_lo)
    an_hi = _clip01(hi[4:6] + c.dt*rate_hi)
    flow_gain = np.asarray(c.q_coeff)
    qss_lo = flow_gain * an_lo * np.sqrt(lo[0])
    qss_hi = flow_gain * an_hi * np.sqrt(hi[0])
    beta = c.dt/c.q_tau
    q_lo = np.maximum(0.0, (1-beta)*lo[1:3] + beta*qss_lo)
    q_hi = np.maximum(0.0, (1-beta)*hi[1:3] + beta*qss_hi)
    h_lo = lo[0] + c.dt/c.reservoir_area*(c.qin_nominal-c.qin_uncertainty-float(q_hi.sum()))
    h_hi = hi[0] + c.dt/c.reservoir_area*(c.qin_nominal+c.qin_uncertainty-float(q_lo.sum()))
    if h_lo <= 0.2: raise ValueError('Height interval leaves monotonic positive domain')
    p_lo = c.turbine_eta*h_lo*float(q_lo.sum())
    p_hi = c.turbine_eta*h_hi*float(q_hi.sum())
    factor = c.dt/c.turbine_inertia
    omega_coef = 1-factor*c.turbine_damping
    w_lo = omega_coef*lo[3]+factor*(p_lo-c.load_nominal-c.load_uncertainty+c.turbine_damping)
    w_hi = omega_coef*hi[3]+factor*(p_hi-c.load_nominal+c.load_uncertainty+c.turbine_damping)
    return np.array([h_lo, *q_lo, w_lo, *an_lo]), np.array([h_hi, *q_hi, w_hi, *an_hi])


def certified_margin(lo: np.ndarray, hi: np.ndarray, u: np.ndarray, c: Config):
    """Positive iff the full uncertainty box maps into the hard safe box."""
    xn_lo, xn_hi = interval_step(lo, hi, u, c)
    return float(min(np.min(xn_lo-np.asarray(c.state_lower)),
                     np.min(np.asarray(c.state_upper)-xn_hi)))


def release_command(lo, hi, requested, fallback, c: Config, grid_size=9, max_checks=100):
    """Only release commands proven feasible. Infeasible backup => None.

    Grid search is a best-effort finite candidate *search*, not a claim that
    absence of a feasible grid point proves global QP infeasibility.
    """
    a = c.command_attack_bound
    if a < 0 or a > 0.5 or max_checks <= 0: raise ValueError('Invalid reserve/budget')
    if (np.any(lo < np.asarray(c.state_lower)) or
            np.any(hi > np.asarray(c.state_upper))):
        return None, 'UNCERTIFIED_INITIAL_SET', None, 0
    candidates = [('PROPOSAL', np.clip(requested,a,1-a)),
                  ('BACKUP', np.clip(fallback,a,1-a))]
    grid = np.linspace(a,1-a,grid_size)
    for p in sorted(((float(np.linalg.norm(np.array([x,y])-requested)),x,y)
                     for x in grid for y in grid)):
        candidates.append(('GRID',np.array([p[1],p[2]])))
    tried=set(); steps=0
    for tag, u in candidates:
        k=tuple(float(v) for v in u)
        if k in tried: continue
        tried.add(k)
        if steps >= max_checks: return None, 'CONTRACT_BUDGET_EXCEEDED', None, steps
        steps += 1
        try: margin = certified_margin(lo,hi,u,c)
        except ValueError: return None, 'UNCERTIFIED_DOMAIN', None, steps
        if margin >= -1e-12:
            return u, 'CERTIFIED_'+tag, margin, steps
    return None, 'NO_CERTIFIED_COMMAND', None, steps


class UnprivilegedController:
    """Production-facing decision boundary: no true plant state or attack flags."""
    def __init__(self, c: Config):
        self.c=c

    def initial_memory(self):
        c=self.c
        return OnlineMemory(np.asarray(c.theta_initial,dtype=float).copy(),
                            np.zeros(6),np.zeros(2),np.zeros(2))

    def decide(self, packet: OnlineInputs, memory: OnlineMemory) -> Decision:
        c=self.c
        local=np.asarray(packet.local_plc_norm,dtype=float)
        hmi=np.asarray(packet.received_hmi_norm,dtype=float)
        reports=np.asarray(packet.federated_reports,dtype=float)
        ages=np.asarray(packet.received_ages,dtype=float)
        updates=np.asarray(packet.reported_updates,dtype=float)
        if (local.shape!=(6,) or hmi.shape!=(6,) or reports.shape!=(c.clients,6)
                or ages.shape!=(c.clients,) or updates.shape!=(c.clients,4)
                or not all(np.all(np.isfinite(v)) for v in (local,hmi,reports,ages,updates))
                or np.any(ages<0)):
            return Decision(None,'INVALID_ONLINE_INPUT',0.0,False,False,None,0)
        # Reuse original PATBU evidence-weighting and clipped four-parameter update.
        med=np.median(reports,axis=0)
        residual=np.linalg.norm(reports-med[None,:],axis=1)
        weights=np.exp(-c.patbu_age_decay*ages)/(1+(residual/c.patbu_residual_scale)**2)
        trust=float(np.clip(np.mean(weights),0,1))
        knowledge=np.average(reports,axis=0,weights=np.maximum(weights,1e-6))
        memory.belief=np.clip(c.patbu_prior_weight*memory.belief +
                              c.patbu_observation_weight*hmi +
                              c.patbu_evidence_weight*knowledge,-4,4)
        _,e=controller_command(memory.belief,memory.theta,memory.integral,c)
        memory.integral=np.clip(memory.integral+c.dt*e,-0.25,0.25)
        proposed,_=controller_command(memory.belief,memory.theta,memory.integral,c)
        # Independently anchored fallback sees ONLY PLC-local telemetry.
        anchor=np.asarray(c.theta_anchor,dtype=float)
        _,eb=controller_command(local,anchor,memory.backup_integral,c)
        memory.backup_integral=np.clip(memory.backup_integral+c.dt*eb,-0.25,0.25)
        backup,_=controller_command(local,anchor,memory.backup_integral,c)
        pred=predict_next(denorm_state(memory.belief,c),proposed,c.qin_nominal,c.load_nominal,c,np.zeros(2))
        spread=float(np.median(np.linalg.norm(reports-med[None,:],axis=1)))
        disagreement=float(np.linalg.norm(hmi-med)/np.sqrt(6))
        risk=(max(0.0,float(np.max(np.maximum(np.asarray(c.state_lower)-pred,
                                              pred-np.asarray(c.state_upper)))))
              +c.gate_disagreement_weight*min(disagreement,2)
              +c.gate_spread_weight*min(spread,2))
        gate=bool(risk<=c.risk_max and trust>=c.q_min)
        if not gate: proposed=backup.copy()
        # Original robust trimmed aggregation and validation (no oracle theta).
        sorted_updates=np.sort(updates,axis=0)
        n=c.byzantine
        if c.clients <= 2*n: return Decision(None,'INSUFFICIENT_VALID_CLIENTS',trust,gate,False,None,0)
        agg=np.mean(sorted_updates[n:c.clients-n],axis=0)
        delta=-c.eta*trust*agg
        for bound in (c.clip_norm,c.trust_region):
            mag=float(np.linalg.norm(delta))
            if mag>bound: delta *= bound/max(mag,1e-12)
        candidate=memory.theta+delta
        xloc=denorm_state(local,c)
        before=trusted_candidate_loss(memory.theta,xloc,memory.integral,c)
        after=trusted_candidate_loss(candidate,xloc,memory.integral,c)
        accept=bool(trust>=c.q_min and np.isfinite(after)
                    and after<=before+c.validation_slack
                    and np.linalg.norm(candidate-anchor)<=0.20)
        if accept: memory.theta=candidate
        lo,hi=state_uncertainty(local,c)
        command,status,margin,work=release_command(lo,hi,proposed,backup,c)
        return Decision(command,status,trust,gate,accept,margin,work)


def in_recovery(x: np.ndarray, c: Config, flow_tol: float, speed_tol: float):
    """True physical recovery predicate, used by offline evaluation only."""
    return bool(np.max(np.abs(np.asarray(x)[1:3]-np.asarray(c.q_ref)))<=flow_tol
                and abs(float(x[3])-1.0)<=speed_tol)


def run_episode(seed: int, scenario: str, c: Config, output: Path,
                flow_tol=0.012, speed_tol=0.008, hold=20):
    """Attack schedule and physical truth exist ONLY in this simulation harness."""
    plant=HydroPlant(c)
    controller=UnprivilegedController(c)
    memory=controller.initial_memory()
    tape=make_tape(seed,c)
    n=c.clients; attack_stop=c.attack_end
    history=[]; trace=[]; contract_fail=None
    for t in range(c.steps):
        physical=scenario in ('physical','joint') and c.attack_start<=t<=c.attack_end
        malicious=scenario in ('knowledge','joint') and c.attack_start<=t<=c.attack_end
        true_before=plant.x.copy()
        local=norm_state(true_before,c)+tape['sensor'][t]
        history.append(local.copy())
        # A compromised HMI stream; independent local PLC measurement is not overwritten.
        hmi=local.copy()
        if physical:
            hmi+=np.asarray(c.physical_observation_bias,dtype=float)
        reports=np.tile(local,(n,1))+tape['client'][t]
        ages=np.zeros(n)
        if malicious:
            reports[n-1]+=np.asarray(c.byzantine_evidence_bias)
            ages[n-1]=4.0
        # Only synthetic local reports reach the analytic gradient generator.
        updates=np.stack([local_gradient(memory.theta,reports[j],memory.integral,c)
                          +tape['update'][t,j] for j in range(n)])
        if malicious:
            updates[n-1]=c.byzantine_gradient_scale*updates[n-1]+np.asarray(c.byzantine_gradient_bias)
        packet=OnlineInputs(local,hmi,reports,ages,updates)
        decision=controller.decide(packet,memory)
        # These truth/coverage checks are offline audit ONLY, never controller inputs.
        lower,upper=state_uncertainty(local,c)
        coverage=bool(np.all(true_before>=lower-1e-12) and np.all(true_before<=upper+1e-12))
        if decision.command is None:
            contract_fail=f'{t}:{decision.status}'
            trace.append(dict(t=t,state_true=true_before.tolist(),command_released=False,
                              status=decision.status,coverage=coverage,safe=safe_state(true_before,c),
                              recovery=in_recovery(true_before,c,flow_tol,speed_tol)))
            break
        # Post-shield corruption is bounded and unknown to the controller.
        post=np.array([-c.command_attack_bound,-c.command_attack_bound]) if physical else np.zeros(2)
        # Recoverable bounded load disturbance induces a genuine physical deviation.
        load=float(tape['load'][t])+(0.010 if physical else 0.0)
        qin=float(tape['qin'][t])
        exogenous_covered=(abs(qin-c.qin_nominal)<=c.qin_uncertainty+1e-12
                            and abs(load-c.load_nominal)<=c.load_uncertainty+1e-12)
        true_after=plant.step(decision.command,qin,load,post)
        in_box=bool(np.all(true_after>=np.asarray(c.state_lower)-1e-12)
                    and np.all(true_after<=np.asarray(c.state_upper)+1e-12))
        trace.append(dict(t=t,state_true=true_after.tolist(),command_released=True,
                          command=decision.command.tolist(),post_attack=post.tolist(),
                          status=decision.status,coverage=coverage,exogenous_covered=exogenous_covered,
                          margin=decision.certified_margin,gate=decision.gate_allowed,
                          accepted=decision.deploy_accepted,work=decision.work,
                          safe=in_box,recovery=in_recovery(true_after,c,flow_tol,speed_tol)))
        if not coverage or not exogenous_covered or not in_box:
            contract_fail=f'{t}:ASSUMPTION_OR_SAFETY_VIOLATION'
            break
    # Attack-end evidence must be outside recovery, then *first* enter for HOLD points.
    at_stop=next((r for r in trace if r['t']==attack_stop),None)
    exposed=bool(at_stop is not None and not at_stop['recovery'])
    first=None
    if exposed and contract_fail is None:
        by_t={r['t']:r for r in trace}
        for t in range(attack_stop+1,c.steps-hold+1):
            if all(by_t.get(k,{}).get('recovery',False) for k in range(t,t+hold)):
                first=t;break
    output.mkdir(parents=True,exist_ok=True)
    raw=output/f'seed_{seed}_{scenario}.jsonl'
    raw.write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in trace),encoding='utf-8')
    return dict(seed=seed,scenario=scenario,steps=len(trace),failure=contract_fail,
                initial_outside_recovery=exposed,corrected=first is not None,
                first_recovery_step=first,recovery_steps_from_attack_stop=(first-attack_stop if first is not None else None),
                violations=sum(not r['safe'] for r in trace),
                certificate_failures=sum(not r['command_released'] for r in trace),
                coverage_failures=sum(not r['coverage'] for r in trace),
                exogenous_coverage_failures=sum(not r.get('exogenous_covered',True) for r in trace),
                n_gate_rejections=sum(not r.get('gate',True) for r in trace),
                mean_margin=float(np.mean([r['margin'] for r in trace if r.get('margin') is not None]))
                            if any(r.get('margin') is not None for r in trace) else None)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='results/tdsc_core_chain_v1')
    p.add_argument('--seed-start',type=int,default=240)
    p.add_argument('--seeds',type=int,default=10)
    p.add_argument('--steps',type=int,default=480)
    a=p.parse_args()
    if a.seeds < 1 or a.steps < 100: p.error('invalid run horizon')
    # Exogenous stochastic draws and transient load are within declared bounds.
    c=replace(Config(),steps=a.steps,qin_uncertainty=0.008,load_uncertainty=0.020)
    path=Path(a.output)
    if path.exists() and any(path.iterdir()):
        raise RuntimeError('Output directory must be empty to prevent evidence overwrite')
    path.mkdir(parents=True,exist_ok=True)
    cases=('clean','knowledge','physical','joint')
    rows=[run_episode(seed,sc,c,path) for sc in cases
          for seed in range(a.seed_start,a.seed_start+a.seeds)]
    with (path/'summary.csv').open('w',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    manifest=dict(experiment='TDSC-R1 unprivileged interval-contract recovery audit',
                  software_only=True,neural_frl_backbone=False,
                  physical_hardware_operated=False,continuous_time_certified=False,
                  interval_contract='one-step discrete HydroPlant Euler inclusion',
                  trusted_inputs='PLC-local bounded observation; known plant bounds and reference controller',
                  attacker_truth_to_controller=False,oracle_shadow_to_controller=False,
                  seed_start=a.seed_start,seeds=a.seeds,scenarios=cases,
                  steps=a.steps,physical_load_stress=0.010,
                  attack_step_start=c.attack_start,attack_step_end=c.attack_end,
                  recovery_flow_tolerance=0.012,recovery_speed_tolerance=0.008,
                  consecutive_recovery_samples=20,results=rows,
                  file_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                               for f in sorted(path.glob('*.jsonl'))})
    (path/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(episodes=len(rows),exposed=sum(r['initial_outside_recovery'] for r in rows),
                          corrected=sum(r['corrected'] for r in rows),
                          failures=sum(r['failure'] is not None for r in rows),
                          per_scenario={s:dict(exposed=sum(r['initial_outside_recovery'] for r in rows if r['scenario']==s),
                                               corrected=sum(r['corrected'] for r in rows if r['scenario']==s),
                                               failed=sum(r['failure'] is not None for r in rows if r['scenario']==s)) for s in cases}),indent=2))


if __name__=='__main__': main()
