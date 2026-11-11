# R4 observed IEEE39 AC equal-byte coordinate-ablation results

> Strictly bounded evidence: 5-client quasi-static AC, not native Simulink.
> Ten independent paired seeds; sample episodes and physical steps are not independent replicates.

| Method | Mean final load (%) | Safe dwell (%) | Restricted score (failures=31) | Uplink bytes |
|---|---:|---:|---:|---:|
| adv | 95.362 | 57.85 | 22.945 | 40,230,000 |
| ordinary | 94.936 | 56.87 | 23.253 | 40,230,000 |
| coord_random | 94.245 | 48.99 | 24.637 | 40,230,000 |
| coord_gradtopk | 95.355 | 58.24 | 22.957 | 40,230,000 |

## Interpretation and limitations
All reported numbers are calculated from SHA256-verified per-run JSON and actual transmitted application bytes.
Random-coordinate and raw-gradient Top-k select k support locations but transmit values from the **same final Adam displacement**.
The original delta-magnitude Top-k and the ordinary-loss Top-k are separate controls.
Censored episodes are **not** treated as 0-step successes; the 31-step restricted score is **not** physical recovery time.
Numerical direction does not imply guaranteed advantage sign, global improvement or Byzantine robustness.
Results may be compared only in the IEEE39 quasi-static AC setting; they are not evidence for the original six-method native figures.

## Paired training-seed uncertainty

| Contrast | Metric | Mean difference | 95% bootstrap CI |
|---|---|---:|---:|
| adv-minus-ordinary | mean_final_load_pct | +0.42527 | [-0.08985, +1.10514] |
| adv-minus-ordinary | safe_dwell_fraction | +0.00980 | [-0.01350, +0.04680] |
| adv-minus-ordinary | mean_restricted_recovery_score | -0.30800 | [-0.81071, +0.11521] |
| adv-minus-ordinary | heldout_load_pct | +0.98340 | [+0.17189, +1.93693] |
| adv-minus-coord_random | mean_final_load_pct | +1.11646 | [+0.29893, +2.03737] |
| adv-minus-coord_random | safe_dwell_fraction | +0.08860 | [+0.01380, +0.21710] |
| adv-minus-coord_random | mean_restricted_recovery_score | -1.69190 | [-3.40312, -0.48959] |
| adv-minus-coord_random | heldout_load_pct | +1.29627 | [-0.04393, +2.80834] |
| adv-minus-coord_gradtopk | mean_final_load_pct | +0.00664 | [-0.05607, +0.06595] |
| adv-minus-coord_gradtopk | safe_dwell_fraction | -0.00390 | [-0.01790, +0.00700] |
| adv-minus-coord_gradtopk | mean_restricted_recovery_score | -0.01250 | [-0.13740, +0.12610] |
| adv-minus-coord_gradtopk | heldout_load_pct | -0.23926 | [-0.55034, -0.02800] |
