"""Independent v5 contract validation prototype. Not G3/G5 certification."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class HoldoutEvidence:
    features: object
    measured_targets: object
    certified: bool
    age: int = 0
    max_age: int = 3

class HeldoutDeploymentValidator:
    def __init__(self, slack=1e-4, max_norm=0.035):
        self.slack, self.max_norm = float(slack),float(max_norm)
    def check(self, current, candidate, evidence):
        before,after=np.asarray(current,dtype=float).ravel(),np.asarray(candidate,dtype=float).ravel()
        info=dict(accepted=False,reason="validation_unavailable",
                  delta_loss=float("nan"),loss_before=float("nan"),loss_after=float("nan"))
        if evidence is None or not evidence.certified or evidence.age>evidence.max_age:
            return info
        x=np.asarray(evidence.features,dtype=float)
        y=np.asarray(evidence.measured_targets,dtype=float).ravel()
        if x.ndim!=2 or x.shape[1]!=before.size or x.shape[0]!=y.size or y.size==0 or after.shape!=before.shape or not all(np.all(np.isfinite(v)) for v in (x,y,before,after)):
            info["reason"]="invalid_evidence"; return info
        if np.linalg.norm(after-before)>self.max_norm+1e-12:
            info["reason"]="step_exceeds_trust_region"; return info
        lb=float(np.mean((x@before-y)**2))
        la=float(np.mean((x@after-y)**2))
        delta=la-lb
        ok=delta<=self.slack
        return dict(accepted=bool(ok),reason="accepted" if ok else "validation_degradation",
                    delta_loss=delta,loss_before=lb,loss_after=la)

def independent_permissions(action_risk_ok, deployment_trust, candidate, current,
                            validator, evidence, min_deploy_trust=0.18):
    decision=validator.check(current,candidate,evidence)
    deploy=bool(decision["accepted"] and deployment_trust>=min_deploy_trust)
    if not deploy and decision["accepted"]:
        decision["reason"]="deployment_trust_gate"
    return dict(action_authorized=bool(action_risk_ok),deploy_accepted=deploy,
                deploy_reason=decision["reason"],validation=decision)

def authorize_proposal_domain(proposal, *, command_limit, attack_budget):
    u=np.asarray(proposal,dtype=float).ravel()
    return bool(u.size and np.all(np.isfinite(u)) and command_limit>=attack_budget>=0
                and np.all(np.abs(u)<=command_limit-attack_budget+1e-12))

def robust_box_intersection(state,proposal,drift,*,state_limit=0.35,
                            command_limit=0.8,post_attack_budget=0.10,
                            dynamics_gain=0.24,disturbance_budget=0.006):
    """Actual-actuator and robust-state constraint INTERSECTION; no unsafe fallback."""
    x=np.asarray(state,dtype=float).ravel()
    u=np.asarray(proposal,dtype=float).ravel()
    d=np.asarray(drift,dtype=float).ravel()
    info=dict(feasible=False,contract_failure=True,reason="invalid_input",
              robust_margin=float("-inf"),realized_input_margin=float("-inf"))
    if (not x.size or u.shape!=x.shape or d.shape!=x.shape
       or not all(np.all(np.isfinite(v)) for v in (x,u,d))
       or dynamics_gain<=0 or state_limit<=0 or command_limit<post_attack_budget
       or disturbance_budget<0):
        return None,info
    g,b,w,L,U=(float(dynamics_gain),float(post_attack_budget),
               float(disturbance_budget),float(state_limit),float(command_limit))
    lo=np.maximum((-L+w-x-d)/g+b,-U+b)
    hi=np.minimum((L-w-x-d)/g-b,U-b)
    info["feasible"]=bool(np.all(lo<=hi+1e-12))
    if not info["feasible"]:
        info["reason"]="empty_robust_state_and_actuator_intersection"
        return None,info
    candidate=np.clip(u,lo,hi)
    margin=float(np.min(L-(np.abs(x+d+g*candidate)+g*b+w)))
    input_margin=float(np.min(U-(np.abs(candidate)+b)))
    if margin < -1e-10 or input_margin < -1e-10:
        info["reason"]="post_projection_contract_violation"
        return None,info
    info.update(contract_failure=False,reason="certified_sampled_box",
                robust_margin=margin,realized_input_margin=input_margin,
                raw_proposal_norm=float(np.linalg.norm(u)),
                intervention_norm=float(np.linalg.norm(candidate-u)))
    return candidate,info
