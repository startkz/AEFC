# IoT-J IoT-76369-2026: strict reproduction ledger (2026-11-02)

## Provenance / locations

- Canonical *physical* testbed repository: `startkz/AEFC`, branch
  `experiment/iotj-76369-ac-grid-bridge-20261102`.
- Original *learning* reference: `startkz/AEFC-FRL` branch
  `review/iotj-76369-evidence-gates`.
- The old `iotj_bridge/core.py` and `run_experiment.py` are **development prototypes**.
- The distinct `iotj_bridge/strict_agent.py`, `strict_run.py`,
  `strict_diagnostic.py`, `strict_audit.py`, and `test_strict.py` are
  the manuscript-aligned candidate for scientific verification.
- Native `experiments/matlab` case39 code remains the prior PATBU/Gate study;
  neither its 560-run plots nor hydropower PI-gain experiments establish
  new results for the present AEFC-FRL learner.

## Implemented as of the recorded commit

| Paper mechanism | Implemented | Validation boundary |
|---|---|---|
| Prioritized replay with TD-error update, alpha=0.6, IS beta=0.4 | yes | local unit test, cloud smoke; full PER calibration still needed |
| Local deterministic actor, two-layer critic, target actors/critics, Polyak tau=.005 | yes | local critic only, no critic exchanged in AEFC |
| Local observation and action adapters, globally shared actor backbone | yes | heterogeneous dimension and action limit tests still in progress |
| Fixed-backbone local optimization and prototype alignment | yes | training enforces gradient boundary |
| Critic-detached positive-advantage weighted sharing loss with fresh Adam state | yes | high-adv empty messages skipped |
| Magnitude Top-k on *resulting* backbone difference | yes | index tie break deterministic, local model restored after sending |
| Utility, prototype drift, clip, normalized weights | yes | client utility not verifiable; susceptible to forged metadata |
| Sparse message byte counting and post-rejection bytes | yes | payload only, **not** wire/TCP/downlink traffic |
| FedRL dense, uniform weighted NoCW, ordinary/rand/TD/high uniform controls | code added | require matched-seed, matched compute, actual-byte audit |
| Critic-sharing A2FC-inspired architecture | code added | NOT original A2FC reproduction; counts are estimated |
| Hard voltage/line safe-action projection | no | observation/penalty only, no hard safety certification |
| Dynamic IEEE39 MATLAB / dynamic IEEE118 with generator frequency | no | independent static pandapower AC, not dynamic case |
| Original submission 1000 episodes x 30 steps and 200 rounds | configurable | no completed independent 10-seed full-budget run yet |
| Original PER-MADDPG full-information baseline | no | scope and fair privacy boundary still unverified |
| Direct reproduction of Qi et al. [40] and original A2FC [59] | no | architecture-control only |
| Original Fig.5-13 numerical reproduction | no | original raw source trajectories not available in this branch |

## Evidence logs (never pool the development prototype with strict runs)

- Strict unit + smoke: GitHub Actions workflow
  `.github/workflows/iotj-76369-strict.yml`.
- Original 65% initial-load smoke success: workflow 41382592109.
  It is a single training seed (80), 5 training episodes, two evaluation
  episodes. Performance from this version must not be attributed to
  subsequent changed demand-profile/heterogeneity implementations.
- 39/118 independent AC interface: `iotj-76369-ac-grid.yml`,
  based on standard static case39 and case118 in pandapower==3.2.1.
- Exploratory matched matrix: `iotj-76369-strict-matrix.yml`
  (`5 train seeds x 2 cases x 3 studies`, 30 episodes).
  Action execution or queueing alone is **not** evidence of completion.
- Strict frozen-surrogate repeated minibatch diagnostic:
  `iotj-76369-strict-frozen.yml` (3 seeds/case, 16 minibatches).
- All workspaces are separate; GitHub upload-artifact retains raw JSON
  for inspection even when jobs fail.

## Security and scientific boundaries

The self-reported client advantage/prototype is attacker-controlled.
Clipping the norm bounds aggregate movement but does not establish
Byzantine robustness. Optional weight clipping is explicitly a new
mitigation and must be tested against honest load/topology shifts.
The current quasi-static AC power-flow only exposes bus voltages and
line/transformer loading; there is no generator-frequency transient,
real-time PLC/HIL, or independently enforced power-flow safety barrier.
`R_load > 90%` alone is not safe recovery; dwell and violations are
separately recorded. Unattained thresholds are failures, not discarded
runs. A deterministic seed is not an independent physical field trial.

## Nonnegotiable resubmission gates

1. **Complete actual manuscript budget:** at least 10 independent training
   seeds with 1000 x 30 interactions and a frozen independent test set.
   Archive raw trajectories, full metadata, model checkpoints and SHA.
2. **Exact matched control:** advantages vs ordinary Top-k, random,
   TD-error, uniform-high, no-prototype, no-adapter, dense FedRL, NoCW,
   correctly constructed critic-sharing and prior [40] baselines.
3. **Adaptive threats:** joint update/metadata spoofing, multiple Byzantine
   clients 1/10, 2/10, 3/10, delayed honest-to-poison and honest shifts.
   Report actual M/N and malicious weight mass.
4. **Physics:** correct safe-set thresholds, voltage, line loading and
   actuator constraints with a safe-action projection and fallback;
   frequency only in a *dynamic* simulator; test operational delays.
5. **Theory:** fixed-surrogate reference-gradient and uncertainty,
   multi-step Adam, masking/clipping and data-dependent weighted direction
   errors. Finite-sample diagnostics do not establish a uniform bound.
6. **Audit:** statistical inference at *train-seed* level, 95% paired CI,
   no conversion of episodes/time samples to independent runs.
7. **Manuscript:** remove/replace all unsupported preexisting numerical
   figures, recompute real bytes, then update Table I and every formal
   response according to actual logs. No resubmission before gates pass.

This ledger is a working scientific audit, not an assertion that all
reviewer and editor comments have been closed.
