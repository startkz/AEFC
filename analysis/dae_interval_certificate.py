#!/usr/bin/env python3
"""Exact rational-box sufficient certificate for a semi-explicit index-1 DAE.

For xdot=f(x,z,u,w), 0=g(x,z,u,w), a parameter-uniform
Krawczyk contraction certifies a unique algebraic root z(x,u,w) in Z;
Picard enclosure certifies the ENTIRE continuous hold interval [0,h] and
the one-step differential state. Exact Fraction interval operations
avoid untracked floating-point roundoff in this mathematical subproblem.

IMPORTANT: The present MathWorks IEEE39 Simscape model has NOT supplied a
validated index-1 reduction, guaranteed interval extensions F/G/J,
trusted all-network state initial enclosure, or physical backup actuator
limits. Therefore this code certifies only models with separately proven
assumptions; passing a small synthetic DAE is NOT native IEEE39 certification.
"""
from dataclasses import dataclass
from fractions import Fraction as Q
from typing import Callable


def frac(x):
    if isinstance(x,Q): return x
    if isinstance(x,str):return Q(x)
    if isinstance(x,float):return Q(str(x))
    return Q(x)


@dataclass(frozen=True)
class I:
    lo: Q
    hi: Q
    def __init__(self,lo,hi=None):
        lo=frac(lo);hi=lo if hi is None else frac(hi)
        if lo>hi:raise ValueError("inverted rigorous interval")
        object.__setattr__(self,"lo",lo)
        object.__setattr__(self,"hi",hi)
    def __add__(self,other):
        other=as_iv(other)
        return I(self.lo+other.lo,self.hi+other.hi)
    __radd__=__add__
    def __neg__(self):
        return I(-self.hi,-self.lo)
    def __sub__(self,other):return self+-as_iv(other)
    def __rsub__(self,other):return as_iv(other)+-self
    def __mul__(self,other):
        other=as_iv(other)
        p=[a*b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return I(min(p),max(p))
    __rmul__=__mul__
    def inside(self,other,strict=False):
        other=as_iv(other)
        return ((other.lo<self.lo and self.hi<other.hi) if strict else
                (other.lo<=self.lo and self.hi<=other.hi))
    def mid(self):return (self.lo+self.hi)/2
    def maxabs(self):return max(abs(self.lo),abs(self.hi))
    def show(self):return [str(self.lo),str(self.hi)]


def as_iv(x):
    if isinstance(x,I):return x
    return I(x)


def matvec(A,v):
    if not A:return []
    if any(len(row)!=len(v) for row in A):raise ValueError("matrix/vector dimension")
    return [sum((as_iv(a)*as_iv(x) for a,x in zip(row,v)),I(0)) for row in A]


def matmul(A,B):
    if not A or not B:return []
    nr=len(B);nc=len(B[0])
    if any(len(row)!=nr for row in A) or any(len(row)!=nc for row in B):
        raise ValueError("matrix product dimensions")
    return [[sum((as_iv(A[i][k])*as_iv(B[k][j])
                   for k in range(nr)),I(0))
             for j in range(nc)] for i in range(len(A))]


def certify_dae(X0, Xtube, Z, U, W, h,
                g_center:Callable, j_z:Callable, f_box:Callable, R,
                safe_x, safe_z, safe_u,
                externally_verified_index1=False,
                validated_inclusion_functions=False,
                verified_initial_set=False,
                verified_disturbance_and_actuator_bounds=False):
    """Return a CONDITIONAL exact-rational mathematical sufficient certificate.

    Callables g_center(Xtube,zmid,U,W), j_z(Xtube,Z,U,W),
    f_box(Xtube,Z,U,W) must already be GUARANTEED INTERVAL EXTENSIONS
    of the original *real* differential/algebraic model. Inexact
    identification, simulation point trajectories or an unconstrained
    local numerical linearization cannot satisfy this requirement.
    """
    rejected={"conditional_mathematical_certificate":False,
              "real_ieee39_network_certified":False,
              "status":"REJECTED"}
    required=(externally_verified_index1,validated_inclusion_functions,
              verified_initial_set,verified_disturbance_and_actuator_bounds)
    if not all(required):
        return {**rejected,"reason":"external index-1/sound interval/initial/actuator evidence missing"}
    h=frac(h)
    n=len(X0);m=len(Z)
    if n<1 or m<1 or h<=0 or len(Xtube)!=n or len(safe_x)!=n or        len(safe_z)!=m or len(R)!=m or any(len(row)!=m for row in R) or        len(U)!=len(safe_u):
        return {**rejected,"reason":"incomplete DAE/input dimensions"}
    X0=[as_iv(t) for t in X0];Xtube=[as_iv(t) for t in Xtube]
    Z=[as_iv(t) for t in Z];U=[as_iv(t) for t in U]
    W=[as_iv(t) for t in W];safe_x=[as_iv(t) for t in safe_x]
    safe_z=[as_iv(t) for t in safe_z];safe_u=[as_iv(t) for t in safe_u]
    if not all(a.inside(b) for a,b in zip(X0,Xtube)):
        return {**rejected,"reason":"initial x set not inside tube"}
    if not all(a.inside(b) for a,b in zip(Xtube,safe_x)):
        return {**rejected,"reason":"differential intersample safe set violated"}
    if not all(a.inside(b) for a,b in zip(Z,safe_z)):
        return {**rejected,"reason":"algebraic intersample safe set violated"}
    if not all(a.inside(b) for a,b in zip(U,safe_u)):
        return {**rejected,"reason":"input uncertainty envelope unsafe"}
    zmid=[q.mid() for q in Z]
    try:
        g=[as_iv(t) for t in g_center(Xtube,zmid,U,W)]
        jac=[[as_iv(x) for x in row] for row in j_z(Xtube,Z,U,W)]
        F=[as_iv(v) for v in f_box(Xtube,Z,U,W)]
        if len(g)!=m or len(jac)!=m or any(len(row)!=m for row in jac)               or len(F)!=n:
            return {**rejected,"reason":"incomplete full DAE nonlinear extensions"}
        RJ=matmul(R,jac)
        remainder=[[I(int(i==j))-RJ[i][j] for j in range(m)]
                   for i in range(m)]
        q=max(sum(remainder[i][j].maxabs() for j in range(m))
              for i in range(m))
        zrad=[Z[i]-I(zmid[i]) for i in range(m)]
        K=[I(zmid[i])-matvec(R,g)[i]+matvec(remainder,zrad)[i]
           for i in range(m)]
        if q>=1 or not all(k.inside(z,strict=True) for k,z in zip(K,Z)):
            return {**rejected,"reason":"uniform algebraic Krawczyk uniqueness test failed",
                    "algebraic_contraction_upper":str(q)}
        tbox=I(0,h)
        candidate=[X0[i]+tbox*F[i] for i in range(n)]
        if not all(candidate[i].inside(Xtube[i],strict=True) for i in range(n)):
            return {**rejected,"reason":"Picard continuous hold-time enclosure failed"}
        endpoint=[X0[i]+I(h)*F[i] for i in range(n)]
        if not all(endpoint[i].inside(safe_x[i]) for i in range(n)):
            return {**rejected,"reason":"discrete one-step endpoint violates safe set"}
        return {"status":"CONDITIONAL_DAE_SOUND_INTERVAL_PASS",
                "conditional_mathematical_certificate":True,
                "real_ieee39_network_certified":False,
                "proof_scope":"only externally validated exact-rational index-1 DAE interval extensions",
                "algebraic_contraction_upper":str(q),
                "uniform_krawczyk_image":[x.show() for x in K],
                "continuous_hold_x_tube":[x.show() for x in Xtube],
                "continuous_hold_algebraic_z_tube":[x.show() for x in Z],
                "sound_one_step_x_box":[x.show() for x in endpoint]}
    except (ValueError,ZeroDivisionError,TypeError,IndexError) as exc:
        return {**rejected,"reason":f"malformed interval model: {exc}"}
