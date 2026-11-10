"""Rule-aware Byzantine message search for the IoT-J R3 experiment.

The adversary observes only its own current sparse upload, previously published
global model increments, previously broadcast prototypes and its own preceding
accepted weight. It NEVER reads honest clients' current messages or held-out AC
evaluation scores. Search is deterministic and has no evaluation-set oracle.
"""
from __future__ import annotations
import math
import numpy as np
import torch
import torch.nn.functional as F

ADAPTIVE_MODES = (
    "adaptive_weight", "adaptive_damage", "adaptive_meta",
    "adaptive_update", "adaptive_proto",
)

def _clip(v, limit):
    n = float(torch.linalg.vector_norm(v))
    return v * min(1., float(limit)/(n+1.e-12))

class AdaptiveServer:
    """Drop-in Server wrapper using the same unmodified utility--drift scorer."""
    def __init__(self, theta, settings, strength=1.0):
        try:
            from .strict_agent import Server
        except ImportError:
            from strict_agent import Server
        self._delegate = Server(theta, settings)
        self.settings = settings
        self.strength = float(strength)
        if not (math.isfinite(self.strength) and 0. <= self.strength <= 2.):
            raise ValueError("strength outside pre-registered range [0,2]")
        self.public_previous_direction = None
        # (self score, self *publicly visible* prior aggregation weight).
        self.previous_self = {}
    @property
    def theta(self):
        return self._delegate.theta
    @property
    def prototypes(self):
        return self._delegate.prototypes

    def _score(self, message):
        cfg = self.settings
        val = np.asarray(message["val"], dtype=np.float32)
        norm = min(float(np.linalg.norm(val)), cfg.clip_update)
        proposed = {k:_clip(torch.as_tensor(v,dtype=torch.float32),
                            cfg.clip_proto) for k,v in message["proto"].items()}
        names = sorted(set(proposed).intersection(self.prototypes))
        drift = (float(np.mean([1.-float(F.cosine_similarity(
            proposed[k].reshape(1,-1),
            self.prototypes[k].reshape(1,-1),dim=1,
            eps=cfg.epsilon_proto).item()) for k in names]))
            if names else 0.)
        utility = min(cfg.cap_utility,max(0.,float(message["utility"])))
        return utility/(norm+cfg.epsilon)*math.exp(-cfg.shift_lambda*drift)

    def _forge(self, original, mode, pos, round_id):
        level = self.strength
        forged = {**original, "idx":np.asarray(original["idx"],dtype=np.int32).copy(),
                  "val":np.asarray(original["val"],dtype=np.float32).copy(),
                  "proto":{k:torch.as_tensor(v,dtype=torch.float32).clone()
                           for k,v in original["proto"].items()}}
        audit = {"candidate_count":0, "objective_value":None,
                 "support_changed":False,"strength":level,
                 "search_prior_only":True}
        if level == 0.:
            return forged,audit
        # Keep category keys, vector dimensions, sparse k and serialized
        # payload length unchanged. The server still applies its real checks.
        if mode != "adaptive_update":
            if mode != "adaptive_proto":
                forged["utility"] = min(self.settings.cap_utility,
                    max(0.,float(original["utility"]))+
                    level*self.settings.cap_utility)
            beta=min(1.,level)
            for k,v in list(forged["proto"].items()):
                if k in self.prototypes:
                    ref=self.prototypes[k].detach().float()
                    if ref.shape==v.shape:
                        forged["proto"][k]=(1.-beta)*v+beta*ref
        if mode in ("adaptive_meta","adaptive_proto"):
            audit["candidate_count"]=1
            audit["objective_value"]=self._score(forged)
            return forged,audit
        old_idx=forged["idx"].copy()
        old_val=forged["val"].copy()
        n=int(original["n"]);k=len(old_idx)
        if not k:
            return forged,audit
        # The previous model increment is visible from successive global
        # checkpoints, not the honest clients' present-round private updates.
        public=(np.asarray(self.public_previous_direction,dtype=np.float32)
                if self.public_previous_direction is not None
                else np.zeros(n,dtype=np.float32))
        if public.shape!=(n,):
            raise ValueError("public direction length mismatch")
        if float(np.linalg.norm(public))>1.e-12:
            chosen=np.argsort(-np.abs(public),kind="stable")[:k]
        else:
            chosen=old_idx.copy()
        chosen=np.sort(chosen).astype(np.int32)
        direction=-public[chosen]
        if float(np.linalg.norm(direction))<=1.e-12:
            origin=dict(zip(old_idx.tolist(),old_val.tolist()))
            direction=-np.asarray([origin.get(int(j),0.) for j in chosen],
                                   dtype=np.float32)
        if float(np.linalg.norm(direction))<=1.e-12:
            direction=np.where(np.arange(k)%2==0,1.,-1.).astype(np.float32)
        direction=direction/(np.linalg.norm(direction)+1.e-12)
        # A public previous-round own weight and the own credibility score
        # recover an estimate of competing-score mass. No current honest
        # utility/update/prototypes and no held-out test rewards are accessed.
        previous=self.previous_self.get(pos)
        rival=(previous[0]*(1./previous[1]-1.) if previous and previous[1]>1.e-9
               else 1.)
        rival=max(1.e-6,min(1.e8,float(rival)))
        cap=min(1.,level)*self.settings.clip_update
        fractions=(0.,.01,.03,.07,.15,.30,.60,1.)
        best=None
        for fraction in fractions:
            candidate={**forged,"idx":chosen.copy(),
                       "val":(direction*(cap*fraction)).astype(np.float32)}
            score=self._score(candidate)
            proxy_weight=score/(score+rival) if score+rival>0 else 0.
            damage=max(0.,-float(np.dot(
                np.bincount(chosen,weights=candidate["val"],minlength=n),
                public)))
            if mode=="adaptive_weight":
                objective=proxy_weight
            elif mode in ("adaptive_damage","adaptive_update"):
                # Maximize the proxy weighted update's opposition to the
                # *previous* public direction (no test-label feedback).
                objective=proxy_weight*damage
                if float(np.linalg.norm(public))<=1.e-12:
                    objective=proxy_weight*float(np.linalg.norm(candidate["val"]))
            else:
                raise ValueError(mode)
            audit["candidate_count"]+=1
            if best is None or objective>best[0]+1.e-15:
                best=(objective,candidate,score,proxy_weight,damage)
        forged=best[1]
        audit.update({"objective_value":float(best[0]),
                      "candidate_score":float(best[2]),
                      "proxy_weight":float(best[3]),
                      "proxy_opposing_update":float(best[4]),
                      "support_changed":not np.array_equal(old_idx,chosen),
                      "candidate_norm":float(np.linalg.norm(forged["val"]))})
        return forged,audit

    def step(self, messages, poisoned=None, attack=None, round_id=0,
             attack_start_round=None):
        if attack not in ADAPTIVE_MODES:
            raise ValueError("AdaptiveServer requires an adaptive mode")
        bad=set(poisoned or ())
        onset=1 if attack_start_round is None else int(attack_start_round)
        if onset<0:
            raise ValueError("negative attack onset")
        forged=list(messages)
        audit={}
        for pos in sorted(bad):
            if pos>=len(messages) or messages[pos] is None or round_id<onset:
                continue
            forged[pos],audit[pos]=self._forge(messages[pos],attack,pos,round_id)
        # The underlying server, clipping, scoring, acceptance checks and
        # optional weight cap are identical to the uncapped baseline.
        result=self._delegate.step(forged,poisoned=bad,attack=attack,
            round_id=round_id,attack_start_round=onset)
        result["attack_strength"]=self.strength
        result["attack_mode"]=attack
        for pos,record in audit.items():
            metric=result["per_client"][pos]
            raw=messages[pos]
            metric.update({
                "attack_search":record,
                "honest_local_utility_before_forgery":float(raw["utility"]),
                "original_sparse_support":np.asarray(raw["idx"]).tolist(),
                "forged_sparse_support":np.asarray(forged[pos]["idx"]).tolist(),
                "actual_utility_change":float(forged[pos]["utility"])-float(raw["utility"]),
                "update_forgery":bool(not np.array_equal(
                    np.asarray(raw["idx"]),np.asarray(forged[pos]["idx"])) or
                    not np.array_equal(np.asarray(raw["val"]),np.asarray(forged[pos]["val"]))),
                "prototype_imitation":bool(any(
                    not torch.equal(torch.as_tensor(raw["proto"][k]),
                                    torch.as_tensor(forged[pos]["proto"][k]))
                    for k in raw["proto"])),
            })
            if metric["accepted"]:
                self.previous_self[pos]=(float(metric["credibility_score"]),
                                         float(metric["aggregation_weight"]))
        # Published model difference/step is available only *after*
        # aggregation, for the next round's attack.
        self.public_previous_direction=result["direction"].detach().numpy().copy()
        result["malicious_accepted_count"]=sum(
            bool(result["per_client"][pos]["accepted"]) for pos in bad
            if pos<len(messages))
        return result
