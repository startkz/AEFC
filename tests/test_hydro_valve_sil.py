"""Local SIL interface tests. These do not certify a PLC or G5 invariance."""
import sys, unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "experiments" / "hydro_valve" if (ROOT / "experiments" / "hydro_valve").exists() else ROOT))
from run_hydro_valve_cps import (CFG, HydroPlant, make_tape, trimmed_mean, predict_next,
     robust_shield, trusted_candidate_loss, norm_state, controller_command)

class HydroValveSILTests(unittest.TestCase):
    def test_deterministic_external_tape(self):
        a,b=make_tape(220,CFG),make_tape(220,CFG)
        self.assertTrue(all(np.array_equal(a[k],b[k]) for k in a))
    def test_separate_seed_changes_disturbance(self):
        a,b=make_tape(220,CFG),make_tape(221,CFG)
        self.assertFalse(np.array_equal(a['sensor'],b['sensor']))
    def test_trimmed_mean_rejects_unbounded_single_byzantine(self):
        arr=np.array([[1.,2.],[1.1,2.1],[.9,1.9],[1.05,2.05],[999.,-999.]])
        self.assertTrue(np.allclose(trimmed_mean(arr,1),[1.05,2.05],atol=.1))
    def test_trimmed_mean_requires_more_than_two_f(self):
        with self.assertRaises(ValueError): trimmed_mean(np.zeros((2,4)),1)
    def test_plant_and_side_effect_free_predictor_agree(self):
        plant=HydroPlant(CFG); x=plant.x.copy(); u=np.array([.75,.83]); post=np.array([.08,-.08]);
        y=plant.step(u,CFG.qin_nominal,CFG.load_nominal,post)
        yp=predict_next(x,u,CFG.qin_nominal,CFG.load_nominal,CFG,post)
        self.assertTrue(np.allclose(y,yp,atol=1e-13))
    def test_receiver_validation_depends_on_candidate(self):
        p=HydroPlant(CFG);x=p.x
        a=trusted_candidate_loss(np.array([.85,.05,.95,.06]),x,np.array([.1,-.1]),CFG)
        b=trusted_candidate_loss(np.array([.1,.5,1.5,.1]),x,np.array([.1,-.1]),CFG)
        self.assertNotEqual(a,b)
    def test_shield_reports_feasible_or_explicit_failure(self):
        x=HydroPlant(CFG).x
        u,intervened,feasible,margin=robust_shield(x,np.array([.8,.8]),np.array([.75,.75]),CFG)
        if feasible:
            self.assertGreaterEqual(margin,-1e-9)
            self.assertTrue(np.all(u>=CFG.command_attack_bound))
            self.assertTrue(np.all(u<=1-CFG.command_attack_bound))
        else:
            self.assertLess(margin,0)
    def test_untrusted_offline_reference_not_used_in_validator(self):
        import inspect
        self.assertNotIn('theta_reference', inspect.getsource(trusted_candidate_loss))
if __name__=='__main__': unittest.main()