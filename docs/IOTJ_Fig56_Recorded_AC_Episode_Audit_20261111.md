# IoT-J Fig. 5/6 — Executed IEEE39 AC training-episode evidence (2026-11-11)

## Scope and provenance

**This is independent supplementary IEEE39 quasi-static AC evidence, not a direct reproduction of the manuscript's original Simulink--Python Fig. 5/6.** The original submitted figure set uses six methods, including a privileged MADDPG implementation that is absent from the runnable AC bridge. The existing `Figures/Convergence-Time.py` and `Figures/Convergence-Accuracy.py` generate synthetic trajectories, not original native simulator logs; they were not used here.

Frozen training source SHA: `0af6e066ff385b191b2db3b86a40adc2ad79956f`  
Executed 50-run workflow: https://github.com/startkz/AEFC/actions/runs/42940416216 — **success (51/51 jobs including independent audit)**  
Audited publication commit: `8452785d175e080be52533ac29aa9997b68589b7`  
Second-pass cross-verification: https://github.com/startkz/AEFC/actions/runs/42951654907 — **success**  
Primary complete raw evidence artifact ID: `13823742485` — https://github.com/startkz/AEFC/actions/runs/42940416216/artifacts/13823742485  
Second-pass result artifact ID: `13824628603` — https://github.com/startkz/AEFC/actions/runs/42951654907/artifacts/13824628603

All 50 tasks: IEEE39, 5 heterogeneous clients, methods `adv`/`ordinary`/`adv_no_cw`/`dense`/`dense_cw`, train seeds 80–89. Each uses 1000 training episodes of 30 recorded steps, 200 completed federated rounds, 10 held-out evaluations. Methods and training protocol match the committed IoT-J strict AC learner. MADDPG was not silently replaced by a different algorithm.

## Evidence integrity

The *first* independent full-budget audit checked each run's unmodified JSON and checkpoint SHA-256, model-source commit, exact training/evaluation budget, first 5-step AC-safe recovery time rederived from stepwise physics, censoring, physical terminal load, and the per-round traffic accounting. The fail-closed report records `passed=true`, `audited_runs=50`, no missing experiments, no errors. The second independent verification then compared:

| Independently cross-checked source | Row count | Status |
|---|---:|---|
| Per-seed × method × episode observations | **50,000** | Pass |
| Real AC physical step observations | **1,500,000** | Pass |
| Per-seed × method summary | **50** | Pass |
| Per-method × episode cross-seed means | **5,000** | Pass |
| Method-level summary | **5** | Pass |

Archived compressed physical-step log SHA-256:
`ef403bea8101ada89b84266f21ec3d3de1288052ac9abbf7f5574ffc8c404fe6`.

The actual recovery predicate is the **first step of five consecutive steps** with ≥90% served load, converged AC power flow, and no voltage/thermal safety violation. If that criterion never holds within the 30-step horizon, the run records `first_safe_dwell_start_step=-1` and `right_censored=1`. The separate restricted recovery *score* assigns 31 to nonrecovery; **31 is not a measured recovery time**. Recovery accuracy is the final served-load-to-demand percentage, not binary recovery success.

## Actual seed-level numerical findings

Each aggregate below is the mean of **ten independent training-seed summaries**, not 10,000 independently replicated episodes. Raw values come from committed `fig56_seed_summary.csv`.

| Method | Mean terminal load (%) | Last 100 episodes terminal load (%) | Episodes with 5-step safe dwell (%) | Restricted recovery score (steps) | Mean censored episodes per 1000 |
|---|---:|---:|---:|---:|---:|
| AEFC-FRL | **95.079** | 96.133 | 58.20 | 23.113 | 418.0 |
| FedRL-OrdTopK | 94.551 | 95.216 | 48.92 | 24.225 | 510.8 |
| FedRL-NoCW | 95.071 | 96.296 | 57.29 | 23.211 | 427.1 |
| FedRL | 94.563 | 95.556 | 53.90 | 23.677 | 461.0 |
| FedRL-NoAdv | 94.931 | 95.891 | 47.27 | 24.089 | 527.3 |

AEFC minus ordinary Top-k has an observed paired mean terminal-load difference of **+0.528 percentage points** and a safe-dwell fraction difference of **+9.28 percentage points** across the ten matched seeds. The numerical comparisons are sample statistics, **not a proven population advantage**. Sensitivity is material: seed 89 alone contributes a +6.368-point terminal-load difference; excluding seed 89 changes the nine-seed average paired difference to about **−0.121 percentage points**. Relative to FedRL-NoCW, AEFC's aggregate mean terminal-load difference is only **+0.0083 percentage points**. Therefore the AC records should not be used to claim unqualified superiority or reproduce the native simulated ranking.

The original manuscript's Fig. 5 expects a physically observed recovery-step curve, whereas the supplementary AC figure plots a **restricted censoring-aware score**; they are different endpoints. The summary and full log preserve both the successful episode's true first safe-dwell start and the censored failure flag. It is incorrect to interpret the restricted mean as the mean recovery time conditional on recovery, or to treat all 1000 episodes as independent statistical units.

## Committed and archived deliverables

Committed to `results/iotj_fig56_episode_traces/`:

- [`fig56_per_episode.csv`](../results/iotj_fig56_episode_traces/fig56_per_episode.csv) — 50,000 original method/seed/episode measurements including each observed first recovery step and censoring status.
- [`fig56_per_seed.csv`](../results/iotj_fig56_episode_traces/fig56_per_seed.csv) — all 50 seed-level summaries and per-run source/checkpoint hashes.
- [`fig56_per_episode_seed_mean.csv`](../results/iotj_fig56_episode_traces/fig56_per_episode_seed_mean.csv) — cross-seed episode means without inventing absent outcomes.
- [`fig56_seed_summary.csv`](../results/iotj_fig56_episode_traces/fig56_seed_summary.csv) — five methods' seed-level means and bootstrap 95% intervals.
- [`fig56_audit_report.json`](../results/iotj_fig56_episode_traces/fig56_audit_report.json) — full-matrix first-stage audit.
- [`fig5_ieee39_ac_supplement.png`](../results/iotj_fig56_episode_traces/fig5_ieee39_ac_supplement.png) and [`fig6_ieee39_ac_supplement.png`](../results/iotj_fig56_episode_traces/fig6_ieee39_ac_supplement.png) — clearly labeled supplementary quasi-static AC curves; they are **not replacement manuscript figures**.

Archival artifacts (separate from small Git commits):

- `fig56_per_step.csv.gz`: **1,500,000** real step records, complete raw physical trajectories, downloadable from run 42940416216's audited artifact, with the SHA-256 above.
- All 50 per-run original JSON, model `.pt` checkpoints and `.manifest.json` SHA-256 source records remain available as per-task artifacts in the same GitHub Actions run.
- Second-pass audit JSON: downloadable from run 42951654907.

## Remaining manuscript evidence gap

The original **six-method Simulink--Python Fig. 5/6 remain unsupported by recovered native per-seed, per-episode logs**. The above result answers the provenance/logging request on the independently executable IEEE39 AC platform, not the literal native reproduction request. Reproducing original Fig. 5/6 requires the exact Simulink environment, six matching algorithm implementations including centralized MADDPG, the original physical stopping rule, frozen protocol, raw trajectories and independent seed-level audit. Nothing here asserts numerical agreement with those missing native sources. No figure in the user-uploaded manuscript has been automatically replaced.
