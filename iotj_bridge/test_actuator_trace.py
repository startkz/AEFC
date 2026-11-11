import unittest
import numpy as np

try:
    from .actuator_trace import apply_actuator_command_limits
except ImportError:
    from actuator_trace import apply_actuator_command_limits


class ActuatorTraceTest(unittest.TestCase):
    def test_saturation_cap_is_reported(self):
        cmd, flag = apply_actuator_command_limits(np.ones(5), "saturation")
        np.testing.assert_array_equal(cmd, np.array([1., .6, 1., .6, 1.]))
        self.assertEqual(flag, 1)

    def test_non_saturation_mode_keeps_commands(self):
        raw = np.array([.2, .4, .6, .8, 1.])
        cmd, flag = apply_actuator_command_limits(raw, "base")
        np.testing.assert_array_equal(cmd, raw)
        self.assertEqual(flag, 0)

    def test_exact_cap_is_not_reported_as_clipping(self):
        raw = np.array([.5, .6, .5, .6, .5])
        cmd, flag = apply_actuator_command_limits(raw, "saturation")
        np.testing.assert_array_equal(cmd, raw)
        self.assertEqual(flag, 0)

    def test_over_cap_is_reported_without_changing_reward_command(self):
        raw = np.array([1.2, .9, .8, .7, .5])
        cmd, flag = apply_actuator_command_limits(raw, "saturation")
        np.testing.assert_array_equal(cmd, np.array([1.2, .6, .8, .6, .5]))
        self.assertEqual(flag, 1)

    def test_lower_bound_violation_is_reported_but_value_is_preserved(self):
        raw = np.array([.2, -.1, .4, .3, .5])
        cmd, flag = apply_actuator_command_limits(raw, "base")
        np.testing.assert_array_equal(cmd, raw)
        self.assertEqual(flag, 1)

    def test_command_values_match_legacy_physics_path(self):
        rng = np.random.default_rng(20261111)
        for mode in ("base", "saturation", "dim_saturation_shift"):
            for _ in range(100):
                raw = rng.uniform(-0.2, 1.2, size=5)
                legacy = raw.copy()
                if mode in ("saturation", "dim_saturation", "saturation_shift", "dim_saturation_shift"):
                    legacy[1::2] = np.minimum(legacy[1::2], 0.6)
                current, _ = apply_actuator_command_limits(raw, mode)
                np.testing.assert_array_equal(current, legacy)


if __name__ == "__main__":
    unittest.main()
