# IoT-J 76369: temporal credibility and per-client drift study protocol

Version: 2026-11-04. This is a prospective protocol. No outcome values are asserted here.

## Scope and code identity

The study uses the existing strict PER actor-backbone AEFC-FRL implementation in `iotj_bridge/strict_run.py`, `iotj_bridge/strict_agent.py`, and the existing pandapower IEEE39 AC steady-state environment. It does not substitute the legacy PATBU/Gate AEFC controller or claim dynamic generator-frequency validation. The primary study is IEEE39 because the reviewer-identified 6% honest demand-shift condition is already implemented there; IEEE118 is not added because the existing AC benchmark saturates on several recovery endpoints.

All variants retain the same learner architecture, 5-client federation, local/actor optimizer settings, PER, shared actor backbone, Top-k ratio, prototype generation, reward, 30-step episode horizon, and 10 held-out evaluation episodes. The only planned changes are attack onset/attack message transformation or the specified `shift_lambda` sensitivity. The original Main Experiment and historical result artifacts remain untouched.

## Study A — credibility establishment before behavior change

### Federation and seeds
- IEEE39; N=5 clients; M=1 malicious client (client ID 4), equal-share reference 0.20.
- Ten independent training seeds: 80--89.
- Exactly 100 federation rounds, five local episodes per round (500 training episodes).
- Ten held-out 30-step evaluation episodes per run.
- Same `--mode adv --hetero dim --batch 256 --hidden 128 --latent 32 --local-steps 5 --sharing-steps 2 --kappa 0.2 --fixed-traffic` settings in every cell.
- Application-layer serialized bytes are retained per round and checked against the byte sum in the run summary.

### Pre-registered conditions
| Condition | Honest rounds before attack | Attack behavior after onset | Physical-channel attack |
|---|---:|---|---|
| Clean | all 100 | none | off |
| Immediate metadata forgery | 1 bootstrap round | utility report x2 (server cap retained), prototype imitation | off |
| Delayed metadata forgery | 5 rounds | same utility and prototype forgery as immediate metadata condition | off |
| Immediate credibility attack | 1 bootstrap round | utility x2, prototype imitation, sign-flipped/scaled sparse update | off |
| Temporal credibility attack | **50 rounds** | same three behaviors as immediate credibility condition | off |

The one-round honest bootstrap is required because the current server prototype reference is created by the first accepted federation round. It ensures that the immediate condition can imitate an existing server prototype; the delayed metadata condition has five full clean rounds before attack, and the temporal credibility condition has fifty. All new timing comparisons keep physical sensing and actuation channels clean. The pre-existing immediate joint physical-plus-knowledge attack remains a separate condition and is not used as the timing-isolation comparator.

The metadata-only pair changes only the onset of utility inflation and prototype imitation; it does not modify update values. The credibility pair changes only the onset of the same three attack transformations. The temporal attacker continues to run the honest local learning code; only its submitted report/prototype/update message is changed at the server boundary after round 50. Utility inflation is multiplied by two before the existing server-side cap. Prototype imitation copies the current server prototype. Update forgery applies the existing sign-flip/scale transform before the unchanged update-norm clipping.

### Logged observables
Every federation round logs, per client: raw and submitted utility, pre-forgery and submitted update norm, post-clipping update norm, prototype drift overall and by category, `exp(-lambda_s * drift)`, credibility score, normalized aggregation weight, weight divided by the equal-share weight, prototype-imitation flag, update-forgery flag, and acceptance status. Global aggregate direction norm, actual serialized uplink bytes, malicious aggregation mass, and attack-phase flag are also retained.

### Primary outcomes and interpretation
1. Malicious-client aggregation-weight trajectory from rounds 1--100.
2. Ratio of malicious weight to the mean honest-client weight.
3. Post-onset cumulative malicious weight mass and global aggregate-direction movement.
4. Detection lag, defined prospectively as the first of **three consecutive post-onset rounds** in which malicious weight / mean honest-client weight is at most 0.25 (equivalent to 0.05 malicious weight under equal 0.20 sharing).
5. Exposure window in local episodes: (detection-start lag rounds + three confirmation rounds) x five episodes. If the criterion is not met, detection is right-censored at the remaining 50 post-onset rounds (250 episodes); no artificial detection time is assigned.
6. Held-out final recovery load, recovery AUC, safe five-step dwell success, and AC voltage/thermal violations.

Ten training seeds are the independent statistical units. Rounds are repeated measures and are not treated as independent samples. Report seed-level means and 95% bootstrap intervals. Do not claim that the attacker is detected within three rounds unless the measured trajectories satisfy the pre-registered criterion. A stable or increasing malicious weight is a negative finding against the current credibility rule.

## Study B — honest-client drift and weight response to abrupt demand shift

### Federation and seeds
- IEEE39; N=5 clients, all honest.
- Ten independent training seeds: 80--89.
- Full 1000 training episodes, 200 federation rounds (five episodes per round), and 10 held-out 30-step test episodes.
- Existing `hetero=shift` operation: at local control step 12 of each episode, the demand of the groups assigned to clients 1 and 3 increases by exactly 6%; clients 0, 2, and 4 are unaffected. No client is malicious and no attack identity is supplied to the server.
- Sensitivity grid: `shift_lambda` in {0, 0.5, 1.0, 2.0}. The no-shift control uses `hetero=dim`, `shift_lambda=1.0`, same seeds and training budget.
- All remaining model, optimization, traffic, and evaluation settings are unchanged.

### Per-client observables
Every round logs the prototype drift (d_i^t), drift penalty (exp(-\lambda_s d_i^t)), raw credibility score, aggregation weight (w_i^t), equal-share weight ratio, update norm, and client ID. Every training and held-out episode logs each client's mean/final served fraction, first step reaching 90% served fraction (or -1 if censored), and actual demand ratio. The demand ratio is independently checked against 1.06 for clients 1/3 and 1.00 for clients 0/2/4.

The 90% local served-fraction time is a per-client service-restoration diagnostic; it is not an independent local AC safety certificate. AC safety remains a system-level property evaluated by the existing voltage and line/transformer thermal constraints.

### Primary outcomes
- Per-client drift and aggregation-weight trajectories over 200 federation rounds at the default (lambda_s=1).
- Mean drift, drift penalty, aggregation weight, weight/equal-share ratio, and held-out local served fraction by client and (lambda_s).
- Shifted clients (1/3) versus unaffected clients (0/2/4), with training seed as the independent unit.
- Paired same-seed shift versus no-shift comparison at (lambda_s=1).
- Global held-out recovery load and safe five-step dwell as secondary outcomes.

The analysis must reveal whether the drift penalty lowers weights for honest clients that experience a legitimate operating change, whether this weight change is concentrated in clients 1/3, and whether it changes local or system-level recovery. A lower client weight alone is not evidence of harmful false rejection; recovery consequences must be reported. If the drift signal is flat or the weight effect is negligible, report that result without inventing an affected client.

## Audit and figure contract

- `iotj_bridge/audit_credibility.py` verifies run budgets, unique client IDs, per-round weight normalization, actual upload-byte sums, training/test counts, checkpoint and JSON SHA-256 manifests, phase boundaries, metadata-only update invariance, and exact 6% client assignment.
- Figure A: temporal credibility and delayed metadata forgery. Two panels compare malicious aggregation-weight trajectories across seeds, with attack onset marked.
- Figure B: per-client prototype-drift and aggregation-weight trajectories at (lambda_s=1), with clients 1 and 3 identified as the shifted groups.
- Table Z: per-client drift, weight, local service restoration, and system recovery sensitivity across (lambda_s\in\{0,0.5,1,2\}), plus paired shift/no-shift differences.
- All charts are generated from the raw per-run JSON after independent audit. No hand-authored curve or target effect is permitted.

## Manuscript claim boundary

These studies evaluate the current utility-drift credibility score in a controlled federated actor-backbone implementation with a quasi-static AC plant. They do not establish cryptographic client authentication, worst-case Byzantine robustness, dynamic frequency stability, or a formal bound on the number of corrupted rounds. The manuscript must report any failure of the current score to downweight a lying client and any reduction in honest shifted-client weights, including their measured recovery consequences.
