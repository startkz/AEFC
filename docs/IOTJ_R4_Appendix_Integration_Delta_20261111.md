# IoT-J R4 — Appendix-ready evidence and reproducibility material

**Status:** standalone integration material for the IoT-J AEFC-FRL manuscript. Appendix numbering and cross-references must be adapted after the correct manuscript source is supplied. This file does not modify the repository's current `main.tex`, `SystemModel.tex`, or `Experimental-RRDRQL.tex`.

## A. Experimental matrices and fixed budgets

### A.1 Equal-byte coordinate-selection experiment

Run **42957084297** used IEEE39 quasi-static AC, training seeds 80–89, five clients, 1,000 training episodes, 200 federated rounds, ten held-out tests per cell, and \(\kappa=0.20\). The matrix contains 40 cells: ten seeds crossed with `adv`, `ordinary`, `coord_random`, and `coord_gradtopk`. The completed batch therefore contains 40,000 training episodes, 8,000 federated rounds, and 400 held-out tests.

For `adv`, `coord_random`, and `coord_gradtopk`, each client computes its complete final two-step Adam displacement before support selection, under the matched positive-advantage objective and minibatch. Within a local sharing step, the coordinate rules select different supports from that method's already-computed displacement and upload the displacement values on those supports. This does not imply that separately trained method trajectories have identical cross-method displacements in later rounds. `ordinary` uses a different, ordinary-loss objective and is an optimization-objective comparator, not a pure coordinate-only ablation.

Every cell uploaded 40,230,000 application-layer bytes (201,150 bytes per round). The independent audit verified equal per-round serialized-byte totals across the four methods within each seed. The 40-cell audit passed, with no missing cells or audit errors. There were 17,805 right-censored training episodes among the 40,000 episodes.

### A.2 Observation/actuator/demand factorial experiment

Run **42959386414** contains the complete \(2^3\) factor matrix crossed with four learning configurations and three training seeds (80–82):

| Factor | Observation | Actuator | Operating demand |
|---|---|---|---|
| `base` | baseline | baseline | baseline |
| `dim` | reduced local observation | baseline | baseline |
| `saturation` | baseline | 0.6 command cap | baseline |
| `shift` | baseline | baseline | 6% step |
| `dim_saturation` | reduced local observation | 0.6 command cap | baseline |
| `dim_shift` | reduced local observation | baseline | 6% step |
| `saturation_shift` | baseline | 0.6 command cap | 6% step |
| `dim_saturation_shift` | reduced local observation | 0.6 command cap | 6% step |

The four configurations are `adv`, `adapter_frozen`, `proto_alignment_off`, and `dense`. The latter three labels must be interpreted precisely: `adapter_frozen` freezes local adapter training while retaining the adapter architecture; `proto_alignment_off` disables local prototype alignment but does not remove all server-side prototype metadata; `dense` is a dense FedRL communication reference and is not an equal-byte comparator.

Each of the 96 cells used 1,000 training episodes, 200 rounds, and ten held-out tests. The complete matrix contains 96,000 training episodes, 19,200 rounds, and 960 held-out tests. This is a **three-seed exploratory factorial study**, not a ten-seed confirmation experiment. The independent statistical unit is the training seed.

Sparse configurations (`adv`, `adapter_frozen`, and `proto_alignment_off`) uploaded 40,230,000 application-layer bytes per cell. The dense configuration uploaded 199,358,000 bytes per cell. These communication budgets must not be described as equal.

### A.3 Applied aggregate-update experiment

Run **42962801194** used seeds 80–89, 1,000 training episodes, 200 rounds, and ten held-out tests per seed. At rounds 50, 100, and 200, the experiment performed three matched physical-profile pre/post comparisons per seed, for 90 paired IEEE39 AC replays. The comparison replaced the shared backbone with the actually aggregated backbone while holding local adapters, action heads, and critics fixed. All 90 applied backbone displacements were nonzero.

## B. Physical-factor intervention checks

The independent physical-intervention recheck for Run 42959386414 passed all 96 cells, 96,000 training traces, and 960 held-out traces.

1. **Observation dimension.** The 48 cells containing the `dim` factor used client observation dimensions \([6,3,6,3,6]\); cells without this factor used \([6,6,6,6,6]\). The corresponding local encoder parameter counts were checked. The shared backbone and action-head geometry remained fixed.
2. **Actuator cap.** The 48 cells containing the `saturation` factor applied a 0.6 command cap to zero-based client indices 1 and 3 before the physical served-load update. The resulting maximum served-fraction increment was 0.0108. The audit checked 2,880,000 constrained training increments; 694,093 reached the cap and none exceeded it. It also checked 28,800 held-out constrained increments; 11,789 reached the cap and none exceeded it.
3. **Demand step.** In the 48 cells containing the `shift` factor, actual AC demand for clients 1 and 3 was multiplied by 1.06 at AC step 12; clients 0, 2, and 4 were unchanged. The step was checked in 48,000 training traces and 480 held-out traces, with zero demand-shift check failures.
4. **Episode-level demand randomization.** Each training episode draws a new seeded load profile. The archived traces contain distinct initial demand profiles across all 1,000 episodes in each cell.

The historical `actuator_saturation` Boolean in the raw JSON is **not** a cap-binding indicator: it was computed after the 0.6 cap and only tested whether the command was outside \([0,1]\). The binding counts above were reconstructed from consecutive observed `client_served_fraction` values. The historical JSON and PT files were not changed. A later output-only logger correction computes the flag before clipping while preserving the exact command vector passed to the physical and reward paths; six unit tests passed in Run **42997543345**. That CI run did not execute training.

## C. Safety recovery and right-censoring definitions

For each physical trace step, the safe predicate is the conjunction of AC convergence, zero voltage-violation excess, and zero thermal-constraint excess. Recovery is the first step belonging to five consecutive steps that satisfy this safe predicate and have at least 90% restored load.

If no such five-step dwell is reached within the 30-step episode horizon, the record is right-censored: `recovery_step = -1` and `censored = 1`. A restricted comparison score of 31 is only a finite-horizon failure code; it is not an observed physical recovery time.

The independent audits recomputed the first five-step dwell from the stored traces and compared it with the recorded recovery step, censoring flag, and safe-dwell flag. The resulting right-censored counts are:

| Batch | Training episodes | Right-censored episodes |
|---|---:|---:|
| Coordinate selection, 40 cells | 40,000 | 17,805 |
| Heterogeneity, 96 cells | 96,000 | 31,613 |
| Applied aggregate update, 10 seeds | 10,000 | 4,206 |

A five-step safe dwell can occur after earlier unsafe steps; it must not be described as an episode that was safe throughout.

## D. Detached SHA256 and raw-artifact integrity

The original raw artifacts were preserved. Separate manifest-audit workflows downloaded the exact source artifacts, re-ran the physical/budget audit, verified the JSON and PT digests against each manifest, and computed detached SHA256 values for every manifest.

| Batch | JSON | PT | Manifest | JSON digest matches | PT digest matches | Detached manifest SHA256 |
|---|---:|---:|---:|---:|---:|---:|
| Coordinate selection | 40 | 40 | 40 | 40/40 | 40/40 | 40/40 computed |
| Heterogeneity | 96 | 96 | 96 | 96/96 | 96/96 | 96/96 computed |
| Applied aggregate update | 10 | 10 | 10 | 10/10 | 10/10 | 10/10 computed |

The coordinate audit rechecked 40,000 episode records, 8,000 round records, 400 held-out records, and equal per-round uplink bytes across the four methods within each seed. The heterogeneity audit rechecked 96,000 episode records, 19,200 round records, 960 held-out records, per-round actual serialized client bytes, physical interventions, and censoring. The aggregate audit rechecked 10,000 episode records, 2,000 round records, 100 held-out records, and 90 paired physical profiles.

The raw artifact SHA256 values are:

- Coordinate artifact 13830018801: `4421bb8a925f27f04d14fa48ac8922ff89f6bf9da6583551ce76b975db89879f`.
- Heterogeneity artifact 13835176012: `82a572cb4b44edf8f9ea5f2262921876b625bc47a3e0a203a7b0b716c152144c`.
- Aggregate-update artifact 13831945798: `759532d8f5af32122b533d5865aac7d97c86515efe98c41434db61033fb45213`.

## E. Advantage-estimation diagnostic and conditional bound

The ten-seed paired AC replay in Run **42958431836** contains 396 sampled-state comparisons under finite-horizon current-policy physical returns. The seed-level results are:

| Diagnostic | Mean | 95% seed-bootstrap CI |
|---|---:|---:|
| Mean absolute advantage-estimation error | 0.05828 | [0.05102, 0.06672] |
| Wrong-positive fraction | 9.78% | [6.30%, 13.50%] |
| Sign-mismatch fraction | 26.66% | [19.72%, 33.59%] |
| Fraction with \(|\widehat A|\leq0.01\) | 46.89% | [42.49%, 52.50%] |

For a fixed policy \(\pi\), the relation

\[
|\widehat A-A^\pi|\leq 2\varepsilon_Q
\]

follows only if both Q estimates at the two comparison points satisfy a genuine common uniform error bound \(|\widehat Q-Q^\pi|\leq\varepsilon_Q\). The finite-horizon sampled replay does not establish such a uniform bound. A positive estimated advantage is not a true-advantage sign certificate, and these data do not prove global aggregation monotonicity or optimal-Q accuracy.

## F. Actual applied aggregate-update result

The ten-seed applied-update experiment passed its independent physical audit: 10/10 seeds, 10,000 training episodes, 2,000 rounds, 100 held-out tests, 90 paired physical profiles, and 4,206 right-censored training episodes. The seed-level paired changes were:

| Checkpoint | Terminal-load change (pp) | 95% CI | Load-AUC change (pp) | 95% CI | Safe-dwell change |
|---|---:|---:|---:|---:|---:|
| 50 rounds | -0.0115 | [-0.0477, 0.0177] | -0.0316 | [-0.0905, 0.0158] | 0 |
| 100 rounds | -0.0079 | [-0.0254, 0.0072] | -0.0451 | [-0.0993, 0.0051] | 0 |
| 200 rounds | -0.0029 | [-0.1549, 0.1401] | -0.0167 | [-0.0734, 0.0268] | -0.0333 [-0.1000, 0] |

The measured shared-backbone updates were nonzero, but these results do not show statistically supported, stable positive recovery improvement. No global monotonicity claim is justified. The short-budget smoke Run **42959621587** remains a functional check only, not performance evidence.

## G. Scope limitations

All added physical results are from the IEEE39 quasi-static AC backend. They do not reproduce the original six-method Simulink–Python Fig. 5/6. They do not establish dynamic frequency safety, a uniform \(\varepsilon_Q\) bound, optimal policy advantage, or global monotonic improvement under federated aggregation. The 96-cell heterogeneity study has three independent training seeds and remains exploratory.

## H. Source commits and artifact entry points

| Evidence | Source code SHA | Result commit | Manifest-audit run / result commit |
|---|---|---|---|
| Coordinate Run 42957084297 | `e674db8b7d00ce908614154bd6f3f21c1a3495ce` | `c5a81519061ea08d445d6c59b79d631b91468027` | Run 42991080229 / `4db9bfa66e04c64013ca48aab27eccd988f9ad77` |
| Heterogeneity Run 42959386414 | `be2d40a4c884a9b6730607e9bbfd8a045e9190db` | `51ba84c7a5d4bf80615fe4b39de7087973adca8e` | Run 42990167631 / `f22392f84f880732fcb8aa125b5f7a5111e5acd3` |
| Applied aggregate Run 42962801194 | `65f28231f3c3d13d8a50893cc99f224edf670faa` | `3f6c98a0f290caa92f49e4d60df8a456efd205bf` | Run 42991863092 / `d812219af934d8841543b24e9afba73ea0aa57a8` |
| Advantage error Run 42958431836 | `e18cc5735c85ed9c1a4bcfad82dfe2391320dd2d` | `9ec371474e9779bcad3da89f9a252c94e61ed3f9` | — |

Direct evidence entry points (the raw ZIPs are immutable; detached-manifest and physical-intervention inventories are separate audit outputs):

- Coordinate raw artifact 13830018801: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13830018801/zip; manifest-audit artifact 13841981672: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13841981672/zip; source run https://github.com/startkz/AEFC/actions/runs/42957084297; manifest audit run https://github.com/startkz/AEFC/actions/runs/42991080229.
- Heterogeneity raw artifact 13835176012: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13835176012/zip; manifest-audit artifact 13841821152: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13841821152/zip; source run https://github.com/startkz/AEFC/actions/runs/42959386414; manifest audit run https://github.com/startkz/AEFC/actions/runs/42990167631.
- Aggregate-update raw artifact 13831945798: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13831945798/zip; manifest-audit artifact 13840799871: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13840799871/zip; source run https://github.com/startkz/AEFC/actions/runs/42962801194; manifest audit run https://github.com/startkz/AEFC/actions/runs/42991863092.
- Advantage-error artifact 13828675696: https://api.github.com/repos/startkz/AEFC/actions/artifacts/13828675696/zip; source run https://github.com/startkz/AEFC/actions/runs/42958431836.
- Actuator telemetry output-only unit tests: https://github.com/startkz/AEFC/actions/runs/42997543345; code commit `26a4e16bea2c9a5a37409d4b7fdc77025e7dac54`.

The manifest inventories contain 40, 96, and 10 detached SHA256 values for the coordinate, heterogeneity, and aggregate batches respectively. The physical-intervention supplement is `results/iotj_r4_hetero_pilot/r4_hetero_physical_intervention_audit.json`. The raw training JSON/PT files and frozen protocol were not changed by either audit supplement.

## I. Manuscript integration boundary

At the evidence snapshot, branch head `5140f4f23950461ead55c8d2273cf33bdd741a5d` still has a `main.tex` that inputs `SystemModel.tex` and `Experimental-RRDRQL.tex` for the separate Bounded-Authority/PATBU/Risk-Gate TDSC manuscript. These files are not the target IoT-J AEFC-FRL manuscript and have not been edited. This appendix-ready material, the standalone integration delta, and the English/Chinese reviewer-response drafts may be integrated only after the correct AEFC-FRL LaTeX source is identified.
