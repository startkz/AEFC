# Response Addendum — six outstanding IoT-J reviewer experiments

**Status: evidence-gated working draft. Do NOT submit until all referenced CI experiments are completed, independently audited and new figures/tables and page numbers are frozen.**

### AE4 / R1.7 / R2.5 — Recovery load versus enforceable physical safety

We thank the Editor and reviewers for pointing out that restored-load percentage alone is not a physical safety criterion. We implemented a prospective, model-predictive AC power-flow action filter, which checks each candidate command before application. For feasible next states it admits only candidates satisfying voltage [0.9,1.1] p.u. and <=100% line/transformer loading; when no candidate is feasible, the safety failure is explicitly recorded instead of being reported as a guarantee. We paired frozen 1000-episode-trained actor checkpoints with and without the execution filter on the same held-out initializations.

**Evidence:** [paired action shield CI](https://github.com/startkz/AEFC/actions/runs/41407891835); exact results and physical violation counts must be inserted after verification.

**Scope:** This is a simulation-enforced AC steady-state action gate, not a dynamic frequency guarantee, hard safety proof for an initially unsafe grid, or HIL/PLC validation.

### R1.10 — Remove oracle attack indicator and count real upload bytes

We removed the attack-status feature entirely from the two-phase traffic signal policy observation; attack scheduling remains known only to the simulator and evaluator. A new independent 15-training-seed experiment compares dense FedRL, FedRL-Clip and the sparse AEFC-interface control. Per-client float32/index/utility uploads are serialized to explicit byte sequences and reported as application-level bytes rather than abstract communication units.

**Evidence:** [oracle-free traffic run](https://github.com/startkz/AEFC/actions/runs/41407990103). Insert run-level queue, recovery success and byte measurements when the run passes.

**Scope:** The traffic policy is a separate queue-control proof of concept, not the full grid PER/actor-backbone model. Wire-level TCP/IP traffic remains unmeasured.

### AE1 / R1.1 / R2.2 — Matched independent high-advantage selection contribution

We explicitly distinguish high-advantage weighted sample selection from ordinary first-N selection, random selection, TD-error selection and uniform weighting of the same positive-advantage subset. We implemented each mode with the same local PER/target actor–critic and optimizer settings, and applied fixed-length Top-k message padding so zero-selection rounds also transmit the same bytes. We run 1000 episodes, 200 federated rounds, 10 independent paired training seeds on IEEE39 and IEEE118. The previously verified matched AEFC-vs-ordinary study is kept as the reference.

**Evidence:** [three newly executed selector workflows](https://github.com/startkz/AEFC/actions/runs/41407429811) and [prior AEFC/ordinary reference](https://github.com/startkz/AEFC/actions/runs/41390041858).

**Reporting rule:** Paired bootstrap intervals use independent training seeds, not time steps. IEEE118 full recovery can cause a ceiling; a non-discriminating result is reported as such.

### AE2 / R1.3 / R2.3 — 10-client cooperative Byzantine attack intensity

We extended the tested population to N=10 and realized M=1/2/3 jointly forged update, self-reported utility and prototype metadata. The original Utility–Drift scorer and an explicitly separate max-weight-cap variant are evaluated with common training seeds and matched scenario definitions. A matching clean M=0/N=10 experiment establishes the non-attacked reference.

**Evidence:** [M/N collaborative CI](https://github.com/startkz/AEFC/actions/runs/41407433389); [clean 0/10 baseline](https://github.com/startkz/AEFC/actions/workflows/iotj-76369-coalition-clean-baseline.yml).

**Security limit:** This is a specified rule-aware joint-message forgery, not a worst-case adaptive optimization attack or a proof of Byzantine tolerance. Per-client cap=0.20 does not cap the total mass of a multi-client coalition to 0.20.

### R1.2 / R1.9 — No-Prototype rerun and semantic comparability

We traced the two failing original No-Prototype tasks to an all-empty-upload edge case in the server return contract. After the bug fix and separate regression verification, we configured a matched same-commit 1000-episode repetition of No-Prototype and complete AEFC on both grids. We additionally estimate per-client support for unsafe/recovering/stable categories, local/global prototype L2 distance, cosine similarity and inter-category separation.

**Evidence:** [matched rerun](https://github.com/startkz/AEFC/actions/runs/41407437933) and [semantic class metrics](https://github.com/startkz/AEFC/actions/runs/41408245276).

**Limit:** Lower prototype distance is empirical alignment, not a proof that unequal-dimensional physical states share causal semantics.

### Membership inference — auditable independent attack evidence

We designed an independent white-box membership experiment with disjoint shadow clients and a target client, retained PER-buffer member candidates and out-of-training-seed nonmember trajectories. Five independently trained seeds per AC grid are attacked using three separate attack seeds each. CSV artifacts preserve every label, predicted membership probability and grouped AUC.

**Evidence:** [independent MIA CI](https://github.com/startkz/AEFC/actions/runs/41407717862).

**Threat caveat:** The stronger white-box attacker accesses local encoder and critic; the honest-but-curious aggregation server does not normally receive these components. Differences in training/evaluation state distributions can also confound measured AUC. We therefore will not describe this as a privacy guarantee for server-only observations.

---

### Required final handoff

For every completed experiment: archive the immutable source commit, per-train-seed metrics, checkpoint hash, physically evaluated test trajectories, method configuration, actual bytes and any missing/failed jobs. Recompute tables and figure captions from those records. Update the clean and fully marked LaTeX manuscript and Cover Letter with exact section and page numbers before resubmission. No claims of completed experiments are permitted for pending jobs.
