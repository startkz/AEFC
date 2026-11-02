# IoT-J 76369 — six outstanding reviewer experiments

**Working ledger, not a claim of completed scientific validation.**
This directory reuses the existing 1000-episode, 200-round local-PER/shared-actor-backbone learner. The IEEE39 and IEEE118 power-flow systems are quasi-static; the IEEE39 MATLAB/Simulink dynamic PATBU/Gate repository is a *different algorithm*.

| Reviewer concern | New implementation | Executed workflow | Required acceptance |
|---|---|---|---|
| Hard-enforced physical control | `iotj_bridge/strict_ac_shield.py` | [AC constraint shield](https://github.com/startkz/AEFC/actions/runs/41407891835) | Prospective AC power-flow solve, only predicted-safe candidate marked feasible, all infeasible states explicitly recorded, shield/no-shield frozen checkpoint comparison |
| Remove oracle attack indicator + measured traffic | `iotj_bridge/traffic_no_oracle.py` | [Traffic without oracle](https://github.com/startkz/AEFC/actions/runs/41407990103) | Policy input excludes attack flag, 15 training seeds, three methods, explicit serialized float32/index/metadata bytes and actual output logs |
| Random/TD-error/Uniform-High selection | `strict_agent.py` existing distinct sharing modes | [Full selection](https://github.com/startkz/AEFC/actions/runs/41407429811) | Two AC grids, 10 matched train seeds, 1000 episodes / 200 rounds, same 40,230,000 application bytes, paired with [original equal-byte AEFC](https://github.com/startkz/AEFC/actions/runs/41390041858) |
| Cooperative Byzantine M/N | `strict_run.py` M, N and joint forged utility/prototype/update | [M/N collaborative attacks](https://github.com/startkz/AEFC/actions/runs/41407433389) and [M0/N10 clean](https://github.com/startkz/AEFC/actions/workflows/iotj-76369-coalition-clean-baseline.yml) | Real 1/10, 2/10, 3/10; 5 paired train seeds; separate original and capped=0.20 cases; record forged weight, safe dwell, byte counts |
| No-prototype regression + semantics | `strict_agent.py` fixed all-empty upload contract; `strict_semantic_audit.py` | [Matched no-proto](https://github.com/startkz/AEFC/actions/runs/41407437933) and [semantic classes](https://github.com/startkz/AEFC/actions/runs/41408245276) | Same SHA for no-proto/with-proto, 3 seeds; local/global prototype L2 and cosine, class support and interclass separation, explicit weak-label caveat |
| Independent MIA | `iotj_bridge/strict_mia.py` | [White-box shadow-client MIA](https://github.com/startkz/AEFC/actions/runs/41407717862) | Ten independent 1000-episode trained targets, three attack seeds each; raw membership labels and probabilities; independent shadows; white-box model access stated |

## Correct scientific boundaries

1. Model-predictive **AC action shielding** is an actual action execution gate in the simulator; it is not frequency-transient stability, full power-system dynamic safety, or formally proven invariance, especially when no feasible next-state candidate exists.
2. The traffic model is a two-phase **non-grid queue proof-of-concept**; removing the oracle input is an independent scenario test but does not make it a 39/118-bus experiment. Application-byte payloads omit link headers, retransmissions, downlink and infrastructure.
3. Full-budget selection mechanisms must be paired at the **training-seed level**, not episode or timestep; an empty high-advantage set uploads an encoded zero message under fixed-byte mode.
4. The capped-weight defense is an **additional variant**, never described as the original AEFC security guarantee. For N=10, cap=.20 bounds any one participant but does not bound the total collusion influence by 0.20.
5. Category prototypes use locally constructed unsafe/recovering/stable indicators, not ground-truth semantic annotations; reduced L2 alone does not establish semantic compatibility of all physical states.
6. The MIA attack is **strong white box** (local encoder and critic exposed). It is not the same adversary as an honest-but-curious federation server, and time/distribution differences between retained replay and unseen rollout can increase or decrease measured AUC.

## Evidence gate

A GitHub Actions run must have a successful result and actual per-seed artifacts before a claim moves from **RUNNING** to **VERIFIED**. Incomplete/missing/failed jobs and unrun seeds are never imputed. Checkpoint hashes, physical trajectories, M/N, sample labels and attack probabilities must remain available. Each response section must reference exact training seed counts, executed commit IDs and figure/table numbers; do not claim that a completed workflow alone proves higher accuracy or Byzantine robustness.

The completed previous 40-job equal-byte reference: https://github.com/startkz/AEFC/actions/runs/41390041858

Remaining separate IoT-J matters outside these six items: faithful source-specific A2FC and Qi et al. [40] baselines, membership attacks with server-only observation, native dynamic frequency, truly wire-level traffic, and consistent clean/marked LaTeX full manuscript.
