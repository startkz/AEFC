# IoT-J 76369: independently audited 30-episode matrix — NOT full budget

**Observed original CI:** https://github.com/startkz/AEFC/actions/runs/41383328642
**Executed commit:** `f2bf401a8dd06ad1ca8e46e9813a488aefbc896d`
**Analysis date:** 2026-11-02

30 artifacts were obtained from the workflow (39/118 x seeds 80–84 x three
studies). 20 jobs were green; ten Byzantine jobs failed in the **auditor**
because it omitted `clients` and `malicious_clients` from trial identity.
Their raw experiment JSON files were present. The auditor was patched in
`iotj_bridge/strict_audit.py` on the working branch.

Across 30 artifacts there are 230 result files representing 210 distinct
trial identities after cross-study duplicate elimination. All 230 JSON records
passed an independent re-check of round sums, actual application uplink bytes,
held-out trace count and five-step safety dwell. A pair of near-identical
duplicate evaluations for case39/seed84 differs in restored load by
~0.0000028 percentage points; this is flagged as a reproducibility difference,
not silently treated as a new independent seed.

## Primary advantage comparison (each 5 paired training seeds, 30 episodes)

| Case | (Adv - ordinary-loss Top-k) mean load difference (percentage points) | Pair-resampled 95% percentile interval |
|---|---:|---|
| 39 | -0.5605 | [-0.8575, -0.2811] |
| 118 | +0.2107 | [-0.0737, 0.5345] |

Intervals are exploratory with only five independent training seeds.
No inference of AEFC advantage improvement or reliable effect is warranted.
Both methods execute 30 training episodes rather than the manuscript
full budget (1000 episodes, 200 federated rounds).

## Adaptive metadata security

Under joint update/metadata forgery, the original self-reported
utility/prototype scoring assigns the malicious member a mean weight of
0.96398 (case39) / 0.97099 (case118), across five training seeds. The
optional separate cap=0.35 rule restricts that weight but does not provide
a Byzantine robustness proof.

## Physical safety

Under the 90%-load and five-consecutive-safe-step criterion:
- case39 `adv`, dim, clean: safe dwell 0/5 seeds;
- case118 `adv`, dim, clean: safe dwell present for all five seeds.
case39 initially lies outside the stipulated thermal safety set in the
65% restoration scenario, so **safe recovery from an unsafe state** must
be distinguished from invariance of an initially safe state.
This AC power-flow backend does not model generator frequency transients
or real actuator dynamics.

## Why this is not a publication claim

1. The old workflow executed from SHA `f2bf401a`, not the later audited
   `strict_run.py` with per-episode provenance checkpoints.
2. The short 30-episode setup is an engineering pilot, not a completed
   1000-episode protocol.
3. The recorded ordinary-loss control and advantage-specific actor
   sharing have different sample selection; exact equal-byte and equal
   optimizer budgets require a final-run audit.
4. Reproducing A2FC or Qi et al. [40] requires source-specific algorithm
   adaptation and control of environmental information; the current
   architectural mock is not equivalent to the original baseline.
5. Physical limits and safe dwell are empirical quasi-static tests only.

Full 1000-episode core reviewer workflow:
https://github.com/startkz/AEFC/actions/workflows/iotj-76369-full1000-core.yml

**Do not re-label these 30-episode numbers as results from that workflow.**
