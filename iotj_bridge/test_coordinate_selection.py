"""Fail-fast tests for coordinate-selection identity and exact serialized budgets.

The frozen replay batch, critic, Adam steps, and final dense displacement
are identical before choosing final coordinates. No synthetic reward result
from this unit test may be reported as physical performance.
"""
import copy
import math
import unittest
import numpy as np
import torch
try:
    from .strict_agent import Agent,flatten,serialized_size
except ImportError:
    from strict_agent import Agent,flatten,serialized_size

class CoordinateSelectionTest(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.agent=Agent(obs_dim=6,seed=311,hidden=32,latent=12,batch=32)
        for i in range(160):
            state=np.array([i%7/7.,(i%11)/11.,.96,.92,(i%13)/13.,i/1000.],
                           dtype=np.float32)
            action=(i%11)/10.
            self.agent.replay.add(state,action,float(.9+action),
                                  state,False,"recovering")
        self.theta=flatten(self.agent.actor.backbone).clone()
        self.batch=self.agent.replay.sample(32)
    def test_three_methods_same_adam_delta_and_bytes(self):
        msgs={}
        for mode in ("adv","coord_random","coord_gradtopk"):
            a=copy.deepcopy(self.agent)
            msgs[mode]=a.share(self.theta,mode=mode,kappa=.20,sharing_steps=2,
                                fixed_batch=self.batch,fixed_traffic=True)
            self.assertIsNotNone(msgs[mode],"No positive advantage; fixture must change")
            msg=msgs[mode]
            self.assertEqual(len(msg["idx"]),math.ceil(.20*len(self.theta)))
            self.assertEqual(len(np.unique(msg["idx"])),len(msg["idx"]))
            self.assertTrue(np.array_equal(msg["idx"],np.sort(msg["idx"])))
            self.assertTrue(np.array_equal(msg["val"],
                np.asarray(msg["uncompressed"])[msg["idx"]]))
            self.assertTrue(torch.equal(self.theta,flatten(a.actor.backbone)),
                            "Share mutated deployed actor")
        x=msgs["adv"]["uncompressed"]
        for mode in ("coord_random","coord_gradtopk"):
            self.assertTrue(np.array_equal(msgs[mode]["uncompressed"],x),
                            mode+" changed original Adam optimization, not just final support")
            self.assertEqual(msgs[mode]["utility"],msgs["adv"]["utility"])
            self.assertEqual(msgs[mode]["selection_count"],msgs["adv"]["selection_count"])
            info=msgs[mode]["coordinate_selection_audit"]
            self.assertEqual(info["k"],len(msgs[mode]["idx"]))
            self.assertEqual(info["dimension"],len(self.theta))
            self.assertTrue(info["same_raw_loss_and_adam_steps"])
            self.assertLessEqual(info["overlap_final_delta_topk"],len(msgs[mode]["idx"]))
            self.assertTrue(np.isfinite(msgs[mode]["val"]).all())
        self.assertEqual(len({serialized_size(m) for m in msgs.values()}),1,
                         "Serialized byte lengths differ under same fixed protocol")
        grad=msgs["coord_gradtopk"]["coordinate_selection_audit"]
        rand=msgs["coord_random"]["coordinate_selection_audit"]
        self.assertIsNotNone(grad["raw_gradient_score_sha256"])
        self.assertIsNone(rand["raw_gradient_score_sha256"])
        self.assertNotEqual(grad["rule"],rand["rule"])
    def test_random_rng_isolated_from_exploration(self):
        start=copy.deepcopy(self.agent)
        alt=copy.deepcopy(self.agent)
        obs=np.ones(6,dtype=np.float32)
        before=start.act(obs,explore=True)
        alt.coord_rng.choice(100,size=20,replace=False)
        after=alt.act(obs,explore=True)
        self.assertAlmostEqual(before,after,places=7)

if __name__=="__main__":
    unittest.main()
