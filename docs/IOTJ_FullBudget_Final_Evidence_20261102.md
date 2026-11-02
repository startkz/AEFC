# IoT-J IoT-76369-2026: full-budget independent evidence audit (2026-11-02)

> **Scientific status: evidence-backed working revision, NOT ready to resubmit.**
> The code in this branch is isolated from the PATBU/Gate AEFC project.

## Source provenance

| Experiment | GitHub Actions | Source commit | Status |
|---|---|---|---|
| Fixed-serialized-byte main Top-kappa paired control | [41390041858](https://github.com/startkz/AEFC/actions/runs/41390041858) | 5d501b1507f68a2d00a8d87f43c244a9ef2e0da3 | 40/40 passed |
| Full-budget adaptive metadata forgery / benign shifts | [41388780044](https://github.com/startkz/AEFC/actions/runs/41388780044) | b086bf34134696dd9da12c68f1bb06cd1805ec87 | 24/24 passed |
| Full-budget heterogeneity / prototype / adapter | [41388932730](https://github.com/startkz/AEFC/actions/runs/41388932730) | 77266adb98dede803719a4c2edad0fc4f840a2e6 | 28/30 passed, 2 failed no-proto |
| Original unequal-byte full-budget matrix | [41388252400](https://github.com/startkz/AEFC/actions/runs/41388252400) | ddc8317159c433ad13fae88de0da0648987cc67d | 28/30 passed; not pooled |
| Fixed PER-Adam frozen gradient snapshot | [41383160172](https://github.com/startkz/AEFC/actions/runs/41383160172) | e597ae6b319ab22e4d32cf443040b15237e24ca5 | Completed |
| Model/physical/episode audit acceptance | [41388552193](https://github.com/startkz/AEFC/actions/runs/41388552193) | fa4f1b0b247173ad5a21ad49a5a79ab44a39699a | Passed |

92 real executed accepted full-budget training runs, each with 10 held-out test episodes, were independently read from original ZIP artifacts (total 920 held-out episodes). All 92 passed manifest checkpoint SHA256, experiment round and episode counts, serialized-byte totals, and recomputed five-step safe recovery. Successful runs and failed jobs remain separate; the 2 failed no-prototype jobs are not imputed.

## Equal-byte, 1000-episode, 200-round paired control

Each case: train seeds 80--89; five clients; 10 held-out test episodes per seed; exactly 40,230,000 bytes of **application-level** uplink per method per run (not network wire bytes).

| Case | Advantage-conditioned Top-k mean +/- SD terminal load | Ordinary Top-k mean +/- SD | Paired load effect [95% seed bootstrap] | Physical safe dwell AEFC / ordinary |
|---|---|---|---|---|
| IEEE39 | 96.287 +/- 4.174 % | 95.256 +/- 4.022 % | +1.0305 pp [0.2080,1.9851] | 64/100 vs 60/100 |
| IEEE118 | 100.000 +/- 0.000 % | 100.000 +/- 0.000 % | 0 pp [0,0]; **complete ceiling** | 100/100 vs 100/100 |

Do not interpret test episodes as independent train runs, nor the raw 64 vs 60 as a statistically established safety effect. IEEE118 ceiling is non-discriminating.

## Full-budget adaptive forgery, three training seeds per condition

| Case | Condition | Terminal load mean | Safe dwell | Malicious weight mean |
|---|---|---:|---:|---:|
| 39 | Joint update + utility + prototype forgery | 90.964% | 0/30 | 0.591 |
| 39 | Separate cap=0.35 mitigation | 93.079% | 12/30 | 0.350 |
| 39 | Delayed joint forgery | 90.964% | 0/30 | 0.581 |
| 39 | Honest demand shift | 100.000% | 30/30 | 0.000 |
| 118 | Joint forgery | 100.000% | 30/30 | 0.603 |
| 118 | Cap=0.35 | 100.000% | 30/30 | 0.350 |
| 118 | Delayed joint | 100.000% | 30/30 | 0.561 |
| 118 | Honest demand shift | 100.000% | 30/30 | 0.000 |

Weight capping is a **new algorithm variant**, not a theorem on the original AEFC. Three seeds are insufficient to conclude universal Byzantine robustness.

## Full-budget single-factor heterogeneity, 28/30 completed

| Case | Sensor mask | 2-step sensor delay | Action saturation | No adapter | No prototype |
|---|---|---|---|---|---|
| 39 safe dwell | 30/30 | 30/30 | 30/30 | 20/30 | 10/20 (n=2 seeds) |
| 118 safe dwell | 30/30 | 30/30 | 30/30 | 30/30 | 20/20 (n=2 seeds) |

The 39/seed80 and 118/seed80 no-prototype jobs failed under the older code with a missing server return key on all-empty uploads. The bug was fixed and a separate regression test passed, but the original run matrix was not retroactively rewritten.

## Fixed surrogate and physical caveats

Strict PER model, 3 seeds x 16 sharing-batch samples after a frozen 30-episode snapshot: empirical bias-direction L2 means 12.29 (case39) and 12.95 (case118); conditional variance-trace means 21.59 and 15.41. These are empirical sample diagnostics, **not a uniform online convergence bound**.

Study safety: quasi-static AC power-flow convergence, voltage in [0.9,1.1] p.u., line/transformer loading <=100%, served load >=90% and five consecutive safe steps. At the case39 initial 65% service, the thermal safety set can be violated. Frozen trained seed82 case39: 30-step test 0/10 safe success for both methods; a distinct 50-step test had 2/10 AEFC vs 0/10 ordinary, **not pooled**.

## Still-open reviewer requirements

1. Faithful A2FC and near-neighbor [40] matched implementation.
2. Dynamic IEEE118 and native IEEE39 generator-frequency and physical actuator verification.
3. A truly enforced safe-action projection / invariance guarantee.
4. Independent membership-inference experiment with raw labels/scores.
5. Non-oracle traffic experiment and actual encoded traffic upload measurements.
6. Independent run-level M/N coordinated attack coverage and complete no-prototype redo.
7. Rebuild the original manuscript plots and marked version from confirmed source records.

The complete 92-run seed-level CSV, 920 held-out episode summary, reviewer response and Chinese audit document are available in the attached user deliverable; do not claim that a repository source commit alone establishes acceptance readiness.
