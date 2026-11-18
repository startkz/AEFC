# IOTJ R5: reviewer 1.3 and 1.5 controlled experiments

Frozen base: `e50c4e35629c7f70331df275c427e5496474e818`. No numeric target is used to tune or select a run. Preserve the existing experiments and original manuscript; do not attribute new statistics to old point estimates unless their underlying records are identified.

## R1.3 — training-endpoint statistics

The archived `results/iotj_fig56_episode_traces/fig56_per_seed.csv` contains 50 audited runs from source commit `0af6e066ff385b191b2db3b86a40adc2ad79956f` (five federated methods, 10 seeds 80–89). It yields AEFC 95.0789% load, 58.20% dwell, 23.113 restricted score, 418 no-dwell episodes per 1000, not the manuscript's 96.80%, 72.40%, 20.74, 276. `r5_archived_statistics.py` reanalyzes only this earlier cohort. Do not attach its intervals to the manuscript table.

The new AC repeat uses seeds 80–89, five clients, 1000 episodes (at most 30 control steps), 200 five-episode synchronization intervals, 10 held-out tests, batch 256, hidden 128, latent 32, five local fitting and two sharing steps, Adam 0.001, kappa 0.2, clean environment, dimension heterogeneity, no fixed packet padding. The five federated arms retain the existing strict implementation. A sixth arm `maddpg_ac` is a **new AC MADDPG-style reconstruction**, using local actors and per-agent centralized critics conditioned on the concatenated joint observations and actions, uniform joint replay, five critic and full actor updates per five-episode interval, no federated messages. It is not the unavailable original Simulink MADDPG implementation, and the optimizer/replay distinctions must be reported. No claim of exact native reproduction is justified.

Every run retains actual per-step observations/physical metrics, episode endpoints, checkpoint and SHA256 manifest. The independent unit is a training seed: terminal served load (%), 5-step safe dwell (%), restricted comparison score (31 on censored episode, not elapsed seconds), and no-dwell count per 1000. For each method: sample mean, sample SD, 20,000 paired-seed percentile bootstrap draws (fixed RNG seed), 95% intervals. For AEFC minus each comparison, compute paired differences, two-sided exact sign-flip p-values (all 2^10 signs; assumption of exchangeable/symmetric differences), and Holm correction across the 20 method-metric contrasts. Report the original manuscript point estimates alongside observed means without forcibly matching them. The new central comparator is never relabeled as the historic native baseline.

## R1.5 — four binary heterogeneity factors, 320 full cells

This is an IEEE39 quasi-static pandapower AC reconstruction using the inspected executable FRL learner, **not** the missing original Simulink-Python training platform. No MATLAB-native controller in this branch implements the paper's identical six-method learner and recovery metrics. The four factor levels are preregistered:

| Factor | 0 | 1 |
|---|---|---|
| M sensing mask | all six channels | minimum-voltage channel zero for C1/C3 |
| D measurement delay | current measurement | two control-step-old mean/min/max voltage for C1/C3; current when history unavailable |
| G attack group | C4 physical attack | C0 physical attack, same attack window/magnitude/count |
| A actuator saturation | [0,1] | cap 0.6 for odd-index clients C1/C3 |

All conditions include exactly one physical corruption (steps 6–16, mean/min voltage +0.12/-0.09 p.u.; command -0.25 clipped), so G isolates the target group, not attack presence. No forged model uploads in this factorial. Delay is applied to clean local voltage history, then physical observation corruption, then mask; command cap precedes attack. C0 and C4 represent different load groups; their physical impact need not be identical. The mask is a fixed-dimensional sensing intervention, not a dimension change. All 16 combinations, including 0000, isolated factors and all interactions, use 5 paired seeds (80–84), 4 arms, identical actual 1000/200/10 budget and matched demand streams. This is the requested factor structure on AC; any claim about the original native platform needs its exact executable control model.

- AEFC full: original learned local encoders/heads, positive advantage sparse sharing, prototypes and utility/drift weighting.
- NoAdapter: replace both trainable local encoder and action head by fixed zero-padding to 32 and sigmoid of the first backbone coordinate; no local learned interface. Critics retain their local observations, and positive-advantage sharing remains. This is literal removal of trainable adapters, not freezing. Fixed interfaces necessarily change actor expressiveness.
- NoProto: retain local adapters but disable local alignment and all prototype exchange, so drift penalties are absent. Real serialized padding maintains the sparse-byte budget.
- FedRL dense: same existing dense uniform aggregation control; not equal-byte because all coordinates are sent.

Report per-seed training metrics and held-out load, dwell, score, failure counts and serialized bytes. For every cell report mean, SD and bootstrap 95% CI; use paired AEFC-control contrasts. For each method estimate all 15 nonempty orthogonal factorial effects on held-out load and dwell, from same-seed contrasts averaged over the other factors. Two-sided exact sign-flip p and Holm-adjusted p supplement intervals; with five seeds the minimum attainable two-sided p is 0.0625, so no conventional exact p<.05 claim can be made. Individual condition contrasts and interactions are exploratory. A zero or negative contrast is retained.

## Execution, auditing and output

Workflows `iotj-r5-main.yml` (60 cells) and `iotj-r5-hetero.yml` (320 cells split across two 160-cell matrices) run on this branch, with pinned PyTorch/pandapower/NumPy. Short smoke tests gate full runs; their outcomes are never used as final measurements. Each full job independently recomputes dwell/censoring and safety from physical traces, validates factor implementation against recorded raw observations/commands, and checks checkpoint hashes. Raw artifacts remain available for 90 days. Only after all predeclared cells from one commit and one run have passed does the summary job commit `results/iotj_r5_main/` or `results/iotj_r5_hetero/`, with seed tables, statistics, paired tests, factorial effects or manuscript reconciliation and audit evidence. Failed/missing runs do not produce completed-cohort conclusions. No native results or exact matches to the manuscript are presumed.
