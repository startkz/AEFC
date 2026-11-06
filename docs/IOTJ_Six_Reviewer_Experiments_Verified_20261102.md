# IoT-J 76369 — six reviewer experiments, independent post-run audit (2026-11-02)

This report supersedes the earlier **pending** statuses in `IOTJ_Six_Reviewer_Experiments_20261102.md`. It distinguishes completed GitHub Actions from inspected raw artifacts. No entry is presented as verified merely because its workflow reported success.

## Provenance

| Study | GitHub Actions run | Original run outcome | Independently inspected |
|---|---|---|---|
| Fixed-byte full-budget Random/TD-error/Uniform-High controls | [41407429811](https://github.com/startkz/AEFC/actions/runs/41407429811) | **60/60 success** | 60 individual ZIP artifacts; 1000 training episodes, 200 rounds, 10 tests, byte totals and model SHA256 reconciled |
| Ten-client M=1/2/3 cooperative poisoning, original/capped | [41407433389](https://github.com/startkz/AEFC/actions/runs/41407433389) | **60/60 success** | 60 original run ZIP artifacts, all checksum/safety/byte/budget checks passed |
| N=10 attack-free controls | [41408532307](https://github.com/startkz/AEFC/actions/runs/41408532307) | **10/10 success** | 10 real-run ZIP artifacts |
| Full-budget paired prototype on/off rerun | [41407437933](https://github.com/startkz/AEFC/actions/runs/41407437933) | **12/12 success** | 12 original ZIP artifacts |
| Frozen-policy minimal-intervention AC shield | [41409094153](https://github.com/startkz/AEFC/actions/runs/41409094153) | **2/2 success** | 2 ZIP artifacts with physical per-step traces |
| White-box shadow-client membership inference | [41407717862](https://github.com/startkz/AEFC/actions/runs/41407717862) | **10/10 success** | 10 ZIP artifacts, labels/scores and 30 AUC values independently recomputed |
| Operational-state semantic prototype measurements | [41408245276](https://github.com/startkz/AEFC/actions/runs/41408245276) | 10 successes, 2 **original audit failures** caused by IEEE118 seed81 floating point `100.00000000000001` | 12 actual immutable JSON results re-audited without retraining, [re-audit CI success](https://github.com/startkz/AEFC/actions/runs/41452265680) |
| Two-phase traffic with no attack-status observation | [41407990103](https://github.com/startkz/AEFC/actions/runs/41407990103) | **1/1 success**, 45 method/seed trials | 15 independent training seeds; actual serialized application payload counts |

**Reproducibility checks:** For the 142 full-budget artifacts in the first four rows, all had exactly 1000 training episode records, 200 federation rounds and 10 unseen evaluation trajectories; checkpoint SHA-256 matched the archived manifest; application byte sums reconciled to all rounds; five-step safety dwell was recomputed from held-out traces. No structural errors were found. Different experiments have different source commits and should be compared only in the planned within-study matched manner.

## Matched recovery-advantage selection (10 paired training seeds, 39-bus)

| Contrast | Load difference, AEFC minus comparator (pp) | Paired seed bootstrap 95% interval (pp) | Safe-dwell tests, AEFC/comparator |
|---|---:|---|---|
| Random | +1.19092 | [+0.05460,+3.03332] | 64/100 vs 50/100 |
| TD-error | +1.03053 | [+0.21032,+1.99280] | 64/100 vs 60/100 |
| Uniform-High-Advantage | **-0.19403** | [-0.53515,+0.07355] | 64/100 vs 69/100 |

All pairs have exactly **40,230,000 application-layer bytes per training seed and method**. Controls use the same 1000-episode/200-round schedule, with the count of selected samples matched to the positive-advantage subset. The Uniform-High result does **not** demonstrate an advantage for numeric advantage weighting over uniform weighting on the *same* positive-advantage transitions. IEEE118 saturates at 100% for all four modes.

## Cooperative M/N metadata poisoning (five seeds/cell, 39-bus)

| M/10 | Original mean load | Cap=0.20 mean load | Original safe-dwell | Capped safe-dwell | Original coalition weight | Capped coalition weight |
|---|---:|---:|---|---|---:|---:|
| 0 | 86.9854% | n/a | 20/50 | n/a | 0 | n/a |
| 1 | 82.2515% | 85.2719% | 0/50 | 10/50 | 0.6578 | 0.2000 |
| 2 | 81.2439% | 84.2000% | 0/50 | 0/50 | 0.5738 | 0.4000 |
| 3 | 82.1038% | 82.3691% | 0/50 | 0/50 | 0.6580 | 0.5519 |

The *0.20 cap is per client*, not an upper bound of 0.20 for the colluding group. At IEEE118, all cells reach 100% and 50/50 safe tests, so that endpoint cannot discriminate robustness. Forged utility/prototype metadata remains an exploitable weakness of the original method.

## Prototype re-run and semantic measurements

Full-budget, same-code matched case39 seeds 80--82: `with_proto` 10/30 safe-dwell tests, `no_proto` **29/30**; the paired load difference (prototype minus no-prototype) is **-3.41484 pp**, exploratory three-seed bootstrap interval [-3.79585,-2.74480]. Case118 is entirely saturated at 100%.

Separate same-scoped 3-seed semantic diagnostics:
- case39 local/global L2 with/no prototype: **0.13321 / 27.76012**; mean cosine **0.99714 / 0.57432**.
- case118 L2: **0.07982 / 18.79221**; mean cosine **0.99787 / 0.53246**.
- The paper cannot equate smaller prototype distance with higher physical recovery performance. Recovery classes are weak operational labels, not externally annotated physical semantics.

## Actual shielded AC action execution, frozen 1000-episode model, seed82

The minimal-intervention policy chooses the feasible candidate closest to the proposed action and simulates the AC constraints **before** execution.

| Case | Shield | Safe five-step tests | Unsafe AC time steps (10x30) | Interventions | Mean terminal load |
|---|---|---:|---:|---:|---:|
| 39 | off | 1/10 | 291 | 0 | 91.9998% |
| 39 | on | **10/10** | 136 | 138 | 99.5639% |
| 118 | off | 10/10 | 0 | 0 | 100% |
| 118 | on | 10/10 | 0 | 0 | 100% |

There are no recorded cases in which a selected AC-predicted feasible action violated the simulated AC limits. The existing initially unsafe states and infeasible candidate steps are not claimed safe; **there is no dynamic frequency, nonlinear transient, hardware, or formal invariance guarantee**. One frozen training seed does not establish a training-level generalization distribution.

## Strong white-box membership inference

Five independent trained targets/case, 3 independent attack seeds/target, 128 target members and 128 target non-members per attack; all prediction labels and probabilities were archived and the AUC recomputed.
- IEEE39 AUC mean **0.52100**, SD **0.05084** across 15 attacks.
- IEEE118 AUC mean **0.51187**, SD **0.03841** across 15 attacks.

The attacker can access local actor, encoder, critic and prototypes; this is strictly *stronger* than a server-only observing sparse messages. Member/non-member temporal distribution mismatch may confound the AUC; these observations do not constitute a DP, information-theoretic, or universal privacy guarantee.

## Oracle-free two-phase traffic benchmark (15 independent seeds per method)

| Method | Mean queue | Mean recovery success | Actual serialized application uplink |
|---|---:|---:|---:|
| AEFC interface PoC | 38.1120 | 23.5733% | 14,400 bytes |
| FedRL | 39.5330 | 36.2133% | 17,600 bytes |
| FedRL-Clip | **24.2781** | **54.1867%** | 17,600 bytes |

AEFC saves **18.18%** of application upload but performs **worse than FedRL-Clip** at traffic recovery under non-oracle sensing. This experiment uses a separate two-phase policy-gradient queue-control PoC rather than the original full PER actor-backbone learner. It does not measure TCP/IP, retransmissions or downlink.

## Manuscript and editor-action boundary

All results must be inserted into the English manuscript with tables, newly numbered figure captions, stable underlying code IDs and explicit limitations. The prior Fig.9 illustrative AUC values cannot be retained as if derived from these newly verified labels/scores. Existing claims of Byzantine tolerance, dynamic IEEE118 safety, model privacy, and uniformly better semantic alignment must be narrowed. A2FC [59] and predecessor [40] remain outstanding source-specific comparisons. This report is evidence, not permission to submit an unreconciled paper.
