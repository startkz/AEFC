import math
import random
import unittest
from fractions import Fraction as Q
from analysis.dae_interval_certificate import I,certify_dae


def g_center(X,zmid,U,W):
    # Exact polynomial g(x,z)=z-(1/5)*x; derivative with respect to z = 1.
    return [I(zmid[0])-I(Q(1,5))*X[0]]


def jacobian(X,Z,U,W):
    return [[I(1)]]


def f_interval(X,Z,U,W):
    # Exact continuous differential model: xdot=-x+z+u+w
    return [-X[0]+Z[0]+U[0]+W[0]]


class NativeDAEConditionalProofTest(unittest.TestCase):
    def setUp(self):
        self.args=dict(
           X0=[I(Q(1,10),Q(11,100))],
           Xtube=[I(Q(9,100),Q(12,100))],
           Z=[I(0,Q(1,20))],
           U=[I(Q(-1,100),Q(1,100))],
           W=[I(Q(-1,100),Q(1,100))],
           h=Q(1,60),
           g_center=g_center,
           j_z=jacobian,
           f_box=f_interval,
           R=[[Q(1)]],
           safe_x=[I(Q(-1,5),Q(1,5))],
           safe_z=[I(Q(-1,10),Q(1,10))],
           safe_u=[I(Q(-1,10),Q(1,10))],
           externally_verified_index1=True,
           validated_inclusion_functions=True,
           verified_initial_set=True,
           verified_disturbance_and_actuator_bounds=True)

    def test_exact_synthetic_dae_safety_end_and_intersample(self):
        result=certify_dae(**self.args)
        self.assertTrue(result["conditional_mathematical_certificate"],result)
        self.assertFalse(result["real_ieee39_network_certified"])
        self.assertEqual(result["algebraic_contraction_upper"],"0")
        endpoint=[Q(q) for q in result["sound_one_step_x_box"][0]]
        rng=random.Random(20261125)
        for k in range(500):
            x0=.1+.01*rng.random()
            u=-.01+.02*rng.random()
            w=-.01+.02*rng.random()
            t=(1./60.)*rng.random()
            # g=0 -> z=x/5; xdot=-0.8*x+u+w exact solution
            offset=(u+w)/.8
            x=offset+(x0-offset)*math.exp(-.8*t)
            z=.2*x
            self.assertLessEqual(.09,x)
            self.assertLessEqual(x,.12)
            self.assertLessEqual(0.,z)
            self.assertLessEqual(z,.05)
            h=1/60
            xend=offset+(x0-offset)*math.exp(-.8*h)
            self.assertLessEqual(float(endpoint[0])-1e-13,xend)
            self.assertLessEqual(xend,float(endpoint[1])+1e-13)

    def test_reject_missing_original_model_interval_evidence(self):
        x=dict(self.args)
        x["validated_inclusion_functions"]=False
        self.assertFalse(certify_dae(**x)["conditional_mathematical_certificate"])
        x=dict(self.args);x["externally_verified_index1"]=False
        self.assertFalse(certify_dae(**x)["conditional_mathematical_certificate"])

    def test_reject_algebraic_nonexistence_or_tight_hold_tube(self):
        x=dict(self.args)
        x["g_center"]=lambda X,z,U,W:[I(z[0])-I(100)*X[0]]
        self.assertIn("Krawczyk",certify_dae(**x)["reason"])
        x=dict(self.args)
        x["Xtube"]=[I(Q(1,10),Q(11,100))]
        self.assertFalse(certify_dae(**x)["conditional_mathematical_certificate"])

    def test_reject_unsafe_input_range(self):
        x=dict(self.args)
        x["U"]=[I(Q(-2,10),Q(1,100))]
        self.assertIn("input",certify_dae(**x)["reason"])


if __name__=="__main__":
    unittest.main()
