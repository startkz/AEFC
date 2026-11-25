"""Fail-closed readiness tests for actual committed IEEE39 state mapping."""
import json
import tempfile
import unittest
from pathlib import Path
from analysis.audit_ieee39_fullstate_gate import inspect

ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'configs/ieee39_fullstate_certification_requirements.json'
MAP=ROOT/'results/ieee39_r2024b/interface_mapping.json'

class NativeFullstateReadinessTest(unittest.TestCase):
    def test_incomplete_native_four_sensor_evidence_remains_blocked(self):
        report=inspect(REG,MAP)
        self.assertEqual(report['status'],'BLOCKED')
        self.assertFalse(report['full_network_certified'])
        self.assertEqual(report['evidence']['mapped_native_sensors'],4)
        self.assertTrue(any('ONLINE_OBSERVER' in x for x in report['blocking_requirements']))
        self.assertTrue(any('NONLINEAR_INTERSAMPLE' in x for x in report['blocking_requirements']))
        self.assertTrue(any('EMERGENCY' in x for x in report['blocking_requirements']))

    def test_manuscript_cannot_set_certification_true_without_evidence(self):
        c=json.loads(REG.read_text())
        c['manuscript_promotion_gate']['full_state_execution_safety_certified']=True
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)/'registry.json'
            t.write_text(json.dumps(c))
            with self.assertRaises(AssertionError):
                inspect(t,MAP)

if __name__=='__main__':
    unittest.main()
