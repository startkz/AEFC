import unittest
import numpy as np
from aefc.validated_interfaces import (HoldoutEvidence,HeldoutDeploymentValidator,
    independent_permissions,robust_box_intersection,authorize_proposal_domain)

class ExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.v=HeldoutDeploymentValidator(slack=1e-4,max_norm=.035)
        self.e=HoldoutEvidence(np.eye(4),np.ones(4)*.01,True)
    def test_beneficial_candidate_accepted(self):
        self.assertTrue(self.v.check(np.zeros(4),np.ones(4)*.01,self.e)["accepted"])
    def test_harmful_candidate_rejected(self):
        self.assertEqual(self.v.check(np.zeros(4),np.ones(4)*-.01,self.e)["reason"],"validation_degradation")
    def test_uncertified_validation_fail_closed(self):
        e=HoldoutEvidence(np.eye(4),np.zeros(4),False)
        self.assertFalse(self.v.check(np.zeros(4),np.zeros(4),e)["accepted"])
    def test_stale_validation_fail_closed(self):
        e=HoldoutEvidence(np.eye(4),np.zeros(4),True,age=8)
        self.assertFalse(self.v.check(np.zeros(4),np.zeros(4),e)["accepted"])
    def test_separate_action_and_deployment(self):
        r=independent_permissions(False,1,np.ones(4)*.01,np.zeros(4),self.v,self.e)
        self.assertFalse(r["action_authorized"]);self.assertTrue(r["deploy_accepted"])
    def test_trust_blocks_deployment_alone(self):
        r=independent_permissions(True,0,np.ones(4)*.01,np.zeros(4),self.v,self.e)
        self.assertTrue(r["action_authorized"]);self.assertFalse(r["deploy_accepted"])
    def test_empty_state_actuator_intersection(self):
        u,r=robust_box_intersection(np.ones(4)*.35,np.zeros(4),np.ones(4)*.3)
        self.assertIsNone(u);self.assertTrue(r["contract_failure"]);self.assertFalse(r["feasible"])
    def test_valid_intersection(self):
        u,r=robust_box_intersection(np.zeros(4),np.zeros(4),np.zeros(4))
        self.assertTrue(r["feasible"]);self.assertGreaterEqual(r["robust_margin"],-1e-10)
    def test_reject_unsafe_fallback(self):
        u,r=robust_box_intersection(np.ones(4)*.35,np.zeros(4),np.ones(4)*.3)
        self.assertEqual(r["reason"],"empty_robust_state_and_actuator_intersection")
    def test_reserve_downstream_actuator_budget(self):
        u,r=robust_box_intersection(np.zeros(4),np.ones(4)*5,np.zeros(4))
        self.assertTrue(np.all(np.abs(u)+.1<=.8+1e-9))
    def test_real_reduced_order_shield_rejects_infeasible(self):
        from aefc.security import RobustBoxShield,ShieldConfig
        box=RobustBoxShield(ShieldConfig())
        u,info=box.project(np.ones(4)*.35,np.zeros(4),np.ones(4)*.30)
        self.assertIsNone(u)
        self.assertTrue(info["contract_failure"])
    def test_real_reduced_order_shield_robust_and_actual_input(self):
        from aefc.security import RobustBoxShield,ShieldConfig
        box=RobustBoxShield(ShieldConfig())
        u,info=box.project(np.zeros(4),np.ones(4)*3,np.zeros(4))
        self.assertIsNotNone(u)
        self.assertTrue(info["feasible"])
        self.assertGreaterEqual(info["realized_input_margin"],-1e-10)
    def test_gate_blocks_out_of_domain(self):
        self.assertFalse(authorize_proposal_domain(np.ones(4)*.06,command_limit=.05,attack_budget=.005))
    def test_gate_allows_inside_domain(self):
        self.assertTrue(authorize_proposal_domain(np.ones(4)*.01,command_limit=.05,attack_budget=.005))
if __name__=="__main__":
    unittest.main()
