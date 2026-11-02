# IoT-J 76369 — first completed 1000 episode paired seed (NOT final multi-seed evidence)

- GitHub Actions run: https://github.com/startkz/AEFC/actions/runs/41388252400
- Frozen code commit: `ddc8317159c433ad13fae88de0da0648987cc67d`
- IEC: quasi-static pandapower IEEE39, training seed 82.
- Both methods: 1000 episodes, 200 completed rounds, 10 held-out evaluations.
- Result artifacts: case39/seed82/adv and case39/seed82/ordinary in the run above.
- Independent auditor verified 1000 training records, 200 rounds,
  serialized application bytes, ten physical test traces and checkpoint SHA-256.

| Metric | Advantage-AEFC | Ordinary-loss Top-kappa |
|---|---:|---:|
| Mean terminal restored load | 91.5071148562% | 90.9612467652% |
| Safe 90% dwell over 5 AC steps | 0/10 | 0/10 |
| Tests with an unsafe physical state | 10/10 | 10/10 |
| Mean sum thermal excess percent over 30 AC steps | 1667.8753 | 1691.1399 |
| Cumulative measured application payload | 40,124,636 bytes | 37,761,290 bytes |

The load difference is +0.5459 percentage points, with +2,363,346 bytes
of communication for Advantage-AEFC. **This is not a matched-byte result
and cannot establish a 10-seed significant difference.**

## Independently frozen 30 vs 50 step safety horizon

https://github.com/startkz/AEFC/actions/runs/41389345719

Same trained actor/critic checkpoints and same held-out initialization:
- 30 steps: both methods 0/10 safe dwell and 0/10 safe-set reentry.
- 50 steps: Advantage-AEFC 2/10 safe dwell and 3/10 safe-set reentry;
  ordinary-loss Top-kappa 0/10 for both.

This deliberately changes the test horizon. The 50-step result must be a
separate sensitivity study and never merged into the 30-step primary outcome.

The current IEEE39 starts outside the chosen thermal safety set. No
invariance theorem is validated from these trajectories. All dynamic
frequency, real-world actuator and dynamic IEEE118 claims remain unresolved.

**Rejection-and-resubmission status: INCOMPLETE**, pending the other
full-budget seeds, matched application bytes, native dynamic validation,
adaptive attacks, personalized representations, A2FC/[40] comparison, MIA,
and non-oracle traffic measurements.
