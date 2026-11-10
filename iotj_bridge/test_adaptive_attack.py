"""Fast R3 invariant tests; no AC backend required."""
import copy
import unittest
import numpy as np
import torch
try:
    from .strict_agent import ServerSettings, Server
    from .adaptive_attack import AdaptiveServer, ADAPTIVE_MODES
except ImportError:
    from strict_agent import ServerSettings, Server
    from adaptive_attack import AdaptiveServer, ADAPTIVE_MODES

def msg(i=0):
    return {"idx":np.array([0,2,4,6],dtype=np.int32),
            "val":np.array([.01,-.01,.005,-.005],dtype=np.float32),
            "n":12,"utility":.1,
            "proto":{"stable":torch.tensor([.2,.4,.3],dtype=torch.float32)},
            "pad_bytes":0}

class TestAdaptive(unittest.TestCase):
    def setUp(self):
        self.theta=torch.zeros(12)
        self.settings=ServerSettings()
        self.messages=[msg(i) for i in range(5)]
    def test_public_only_and_fixed_shape(self):
        s=AdaptiveServer(self.theta,self.settings,strength=1)
        s.step(self.messages,poisoned=(4,),attack="adaptive_damage",round_id=0,
               attack_start_round=1)
        before=copy.deepcopy(s._delegate)
        a,ameta=s._forge(self.messages[4],"adaptive_damage",4,1)
        # A changed honest client's *current-round* private message must not
        # influence the forged message at the same public state.
        z=[msg(i) for i in range(5)]
        z[0]["utility"]=999.
        b,bmeta=s._forge(z[4],"adaptive_damage",4,1)
        self.assertTrue(np.array_equal(a["idx"],b["idx"]))
        self.assertTrue(np.array_equal(a["val"],b["val"]))
        self.assertEqual(a["utility"],b["utility"])
        self.assertEqual(len(a["idx"]),len(self.messages[4]["idx"]))
        self.assertLessEqual(np.linalg.norm(a["val"]),self.settings.clip_update+1.e-7)
        self.assertEqual(set(a["proto"]),set(self.messages[4]["proto"]))
    def test_strength_zero_is_identity(self):
        for mode in ADAPTIVE_MODES:
            s=AdaptiveServer(self.theta,self.settings,strength=0)
            m,_=s._forge(self.messages[4],mode,4,1)
            self.assertEqual(m["utility"],self.messages[4]["utility"])
            self.assertTrue(np.array_equal(m["val"],self.messages[4]["val"]))
            self.assertTrue(np.array_equal(m["idx"],self.messages[4]["idx"]))
    def test_weight_objective_accepts_and_normalizes(self):
        s=AdaptiveServer(self.theta,self.settings,strength=1)
        s.step(self.messages,poisoned=(4,),attack="adaptive_weight",round_id=0,
               attack_start_round=1)
        stats=s.step(self.messages,poisoned=(4,),attack="adaptive_weight",round_id=1,
                     attack_start_round=1)
        self.assertEqual(stats["accepted"],5)
        self.assertAlmostEqual(sum(x["aggregation_weight"] for x in stats["per_client"]),1.,places=6)
        self.assertGreater(stats["malicious_weight"],0.)
        self.assertEqual(stats["per_client"][4]["attack_search"]["candidate_count"],8)
    def test_weight_cap_applied_not_implied_security(self):
        settings=ServerSettings(max_weight=.20)
        s=AdaptiveServer(self.theta,settings,strength=1)
        s.step(self.messages,poisoned=(4,),attack="adaptive_damage",round_id=0,
               attack_start_round=1)
        stats=s.step(self.messages,poisoned=(4,),attack="adaptive_damage",round_id=1,
                     attack_start_round=1)
        self.assertLessEqual(stats["malicious_weight"],.20+1.e-8)
    def test_no_attack_on_first_clean_round(self):
        s=AdaptiveServer(self.theta,self.settings,strength=2)
        res=s.step(self.messages,poisoned=(4,),attack="adaptive_damage",round_id=0,
                   attack_start_round=1)
        self.assertFalse(res["per_client"][4]["attack_active"])
        self.assertNotIn("attack_search",res["per_client"][4])

if __name__=="__main__":
    unittest.main()
