from __future__ import annotations

import numpy as np

SATURATION_MODES = frozenset({
    "saturation", "dim_saturation", "saturation_shift", "dim_saturation_shift"
})


def apply_actuator_command_limits(actions, hetero: str):
    """Apply the existing command cap and report whether any cap bound.

    This preserves the pre-existing command values exactly: it only applies
    the same 0.6 upper cap to odd-indexed clients in saturation modes. It
    deliberately does not clamp to [0, 1], because the physical transition
    already performs that clamp and the reward uses the capped command value.
    """
    raw = np.asarray(actions, dtype=float).copy()
    cmd = raw.copy()
    upper = np.ones_like(cmd)
    if hetero in SATURATION_MODES:
        upper[1::2] = 0.6
        cmd[1::2] = np.minimum(cmd[1::2], 0.6)
    saturated = bool(np.any(raw < 0.0) or np.any(raw > upper + 1e-12))
    return cmd, int(saturated)
