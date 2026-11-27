"""Purely SYNTHETIC statistics semantics; not IEEE39 physical outcomes."""
import unittest
from analysis.ieee39_recovery_stats import analyze,exact_paired_sign_p

def pair(seed,a_exposed,b_exposed,a_recovered,b_recovered,ta,tb):
    return dict(seed=seed,pressure=0.12,scenario='joint',
      both_at_attack_end_exposed=a_exposed and b_exposed,
      ae_fc_exposed=a_exposed,supervisor_exposed=b_exposed,
      ae_fc_recovered=a_recovered,supervisor_recovered=b_recovered,
      ae_fc_recovery_time=ta,supervisor_recovery_time=tb,
      ae_fc_speed_error=.2,supervisor_speed_error=.3,
      supervisor_minus_ae_fc_speed_error=.1)
class TestRecoveryEvidence(unittest.TestCase):
    def test_nonexposure_must_not_become_recovery(self):
        d={'full_network_safety_certified':False,
           'paired_ae_fc_supervisor':[pair(i,False,False,False,False,None,None) for i in range(10)]}
        x=analyze(d)
        self.assertEqual(x['both_exposed_conditions'],0)
        self.assertEqual(x['independent_seeds_with_both_exposure'],0)
        self.assertFalse(x['statistical_mechanism_recovery_gain_established'])
        self.assertFalse(x['manuscript_ready_full_AEFC_recovery_claim'])
    def test_censored_right_tail_penalized_in_recovery_time(self):
        d={'full_network_safety_certified':False,
           'paired_ae_fc_supervisor':[pair(i,True,True,True,False,.35,None) for i in range(10)]}
        x=analyze(d)
        self.assertEqual(x['both_exposed_recovered_AEFC'],10)
        self.assertEqual(x['both_exposed_recovered_Supervisor'],0)
        self.assertAlmostEqual(x['paired_restricted_time_to_recovery_improvement_seconds']['mean'],1.2-.35)
        self.assertEqual(x['paired_recovery_exact_sign_test']['p_two_sided_exact'],2/1024)
        self.assertTrue(x['statistical_mechanism_recovery_gain_established'])
        self.assertFalse(x['manuscript_ready_full_AEFC_recovery_claim'])
    def test_exposure_prevention_does_not_count_as_recovery(self):
        d={'full_network_safety_certified':False,
           'paired_ae_fc_supervisor':[pair(i,False,True,False,True,None,.25) for i in range(10)]}
        x=analyze(d)
        self.assertEqual(x['prevented_exposure_conditions_AEFC_only'],10)
        self.assertEqual(x['both_exposed_conditions'],0)
        self.assertEqual(x['both_exposed_recovered_AEFC'],0)
        self.assertFalse(x['statistical_mechanism_recovery_gain_established'])
    def test_small_sample_cannot_prove_significance(self):
        d={'full_network_safety_certified':False,
           'paired_ae_fc_supervisor':[pair(i,True,True,True,False,.1,None) for i in range(2)]}
        x=analyze(d)
        self.assertFalse(x['statistical_mechanism_recovery_gain_established'])
        self.assertEqual(x['paired_recovery_exact_sign_test']['p_two_sided_exact'],.5)

if __name__=='__main__':
    unittest.main()
