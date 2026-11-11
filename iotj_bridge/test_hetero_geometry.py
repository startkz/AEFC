"""Executable contract for observation/actuation/operating-shift factors.

These checks verify actual physics-control interfaces and model geometry,
not semantic compatibility or restored-load superiority.
"""
import unittest
import numpy as np
import torch
try:
    from .strict_run import RecoveryGrid
    from .strict_agent import Agent
except ImportError:
    from strict_run import RecoveryGrid
    from strict_agent import Agent

HETERO={
    "base": [6,6,6,6,6],
    "dim": [6,3,6,3,6],
    "saturation":[6,6,6,6,6],
    "shift":[6,6,6,6,6],
    "dim_saturation_shift":[6,3,6,3,6],
}
class GeometryContract(unittest.TestCase):
    def test_each_physical_factor_and_combination(self):
        for mode,expected in HETERO.items():
            g=RecoveryGrid(39,5,80,mode,attack="clean")
            obs=g.reset()
            self.assertEqual([len(x) for x in obs],expected)
            before=g.served.copy()
            g.step(np.ones(5))
            delta=g.served-before
            expected_step=.018*(.6 if mode in ("saturation","dim_saturation_shift") else 1.)
            self.assertAlmostEqual(float(delta[1]),expected_step,places=7)
            self.assertAlmostEqual(float(delta[0]),.018,places=7)
            demand_seed=g.demand.copy()
            for _ in range(11):g.step(np.full(5,.5))
            is_shift=mode in ("shift","dim_saturation_shift")
            expected_demand=demand_seed.copy()
            if is_shift:
                for group in g.groups[1::2]:expected_demand[group]*=1.06
            self.assertTrue(np.allclose(g.demand,expected_demand,rtol=1e-9),
                            "Operating-shift factor mismatch: "+mode)
            a=[Agent(dim,seed=800+i,hidden=128,latent=32)
               for i,dim in enumerate(expected)]
            b=[sum(p.numel() for p in q.actor.backbone.parameters()) for q in a]
            self.assertEqual(len(set(b)),1)
            enc=[sum(p.numel() for p in q.actor.encoder.parameters()) for q in a]
            if mode in ("dim","dim_saturation_shift"):
                self.assertNotEqual(enc[0],enc[1])
            self.assertEqual(a[0].actor.encoder[-1].out_features,32)
    def test_adapter_freeze_does_not_remove_encoder(self):
        c=Agent(3,seed=100,hidden=32,latent=12,batch=16)
        enc_params=sum(p.numel() for p in c.actor.encoder.parameters())
        self.assertGreater(enc_params,0)
        self.assertIsNotNone(c.actor.head)
        # Flag --disable-adapters suppresses local adapter training; its
        # architecture remains present. Must not label as no-adapter topology.

if __name__=="__main__":
    unittest.main()
