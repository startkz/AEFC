# IoT-J 76369 — Reviewer 3: temporal credibility and isolated metadata timing (independent completed audit)

**Status:** Fifty of fifty complete experiment jobs and one audit job succeeded in [GitHub Actions run 41790844600](https://github.com/startkz/AEFC/actions/runs/41790844600). A second, independent local audit inspected the original 50 ZIP artifacts, verified all 50 JSON SHA-256 digests against their manifests and all 50 model-checkpoint SHA-256 digests, and recomputed 100 synchronization rounds, 500 train episodes, 10 held-out tests, serialized bytes, client-score/weight normalization, and attack-onset boundaries. Original experiment commit: `1c0cc5a9db0b2cde232b90a86926053c4c6971bf`.

## Scientific configuration

IEEE39 quasi-static AC, N=5 clients, one designated attacker (client ID4), training seeds80–89, 500 train episodes (=100 federated rounds ×5 episodes), 10 held-out 30-step test episodes, Top-k 20%, 128 hidden, 32 latent, same PER/actor-backbone/critic. Each run transmits exactly **20,115,000** serialized application-layer uplink bytes. All conditions omit physical-channel attacks. Attack conditions:
- **Clean:** all 100 rounds honest.
- **Immediate metadata:** one honest bootstrap round; utility inflated ×2 (server cap preserved) and current server prototype imitated starting round2; *unchanged model update values*.
- **Delayed metadata:** five honest rounds; identical metadata-only forgery starting round6; *unchanged model update values*.
- **Immediate combined:** one honest bootstrap round; utility inflation, prototype imitation and sign-flipped/scaled update from round2.
- **Temporal combined:** 50 honest rounds; same combined forgery starting round51. Client local learner continues to operate; server receives forged message only after phase switch.

The one-round bootstrap is needed because the current server does not possess a previous prototype before federation round1. These metadata-only comparisons isolate timing without the original immediate joint physical-channel corruption.

## Measured outcomes, n=10 independent trained seeds

| Condition | Mean designated client weight, rounds 51–100 | Five-step safe recoveries / 100 held-out episodes |
|---|---:|---:|
| Clean | 0.1537 | 60 |
| Immediate metadata-only | 0.2446 | 60 |
| Delayed metadata-only | 0.2910 | 60 |
| Immediate combined forgery | 0.3174 | 40 |
| Honest-50-then-combined forgery | **0.3176** | 60 |

The temporal attack's client4 weight mean in the *last ten honest rounds* is **0.0856**, in the *first ten post-onset rounds* it is **0.1874**, and across all post-onset rounds it is **0.3176**. In round-aligned, seed-paired comparisons with clean client4, the post-onset weight increase is **+0.1638788** with seed-bootstrap 95% CI **[+0.1138230,+0.2120820]** (20,000 bootstrap resamples). The late-stage difference is positive; the existing utility–drift weight does **not** suppress the participant after its behavior changes.

A post-onset low-weight diagnostic, defined as client4's weight divided by the honest-client mean at most 0.25 for three consecutive rounds, occurs for only **one of ten** temporal-attack training seeds. Across the ten temporal experiments, **60 three-round low-weight windows were also observed before the attack** in the honest phase. These are overlapping repeated windows; **they are not independent alarms and do not estimate a false-positive rate.** The model has no authenticated malicious identity detector or persistent per-client reputation ledger; a low weight is only an empirical diagnostic, not a detection event.

Final restored-load means across the five respective conditions are 95.4619%, 95.4139%, 95.0485%, 94.5506%, and 96.0312%. Higher terminal restoration under a late attack is partly explained by fewer attacked rounds and must not be interpreted as successful credibility-based detection.

## Critical causal and reproducibility boundary

The implementation's trust score is **instantaneous per federation round**, `s_i=clip(utility_i)/(||clip(update_i)||+eps)×exp(-lambda_s×prototype_drift_i)`; there is no cross-round history accumulator. The first 50 rounds of each temporal run are verified to contain unmodified client messages, but identically numbered clean and temporal jobs were executed on separate hosted workers. Of 40 matched pre-attack condition/seed comparisons, 20 produced bitwise-equal trajectories; the others accumulated floating-point/optimizer differences. Accordingly, *equal PRNG seeds are not evidence of identical clean pre-histories*, and no such false assertion is used in the response.

The observed failure to downweight is specific to the current utility–drift heuristic, its trained policy, and this IEEE39 AC protocol. It does not show universal physical failure, and the steady-state solver does not test generator frequency transients. No claim of 1–3-round attack identification or weight falling below 0.05 is supported.

## Figures, table, and reproducibility

- GitHub Actions source: [50 raw artifacts and audit ZIP](https://github.com/startkz/AEFC/actions/runs/41790844600).
- Run-specific original implementation: `iotj_bridge/strict_agent.py`, `strict_run.py` and workflow `iotj-76369-credibility-timing.yml` at commit `1c0cc5a9db0b2cde232b90a86926053c4c6971bf`.
- Current independent audit and plotting script: `iotj_bridge/audit_credibility.py` on this feature branch. New logged per-client fields include raw/reported utility, prototype drift, drift penalty, update norm, normalized aggregation weight and score.
- Graph caption: *Aggregation weight of the designated client under early versus delayed message forgery (n=10 independent training seeds; seed means and pointwise 1.96 standard-error bands).* Figure must not be labeled a learned long-term reputation trajectory.
- Planned further companion: per-client honest 6% load-shift and same-observation-dimension round51 phase difference-in-differences studies are separate, not results asserted by this file.

**Editorial conclusion:** The experiment resolves the lack of testing but exposes a substantive security limitation. The manuscript and Response should acknowledge it, rather than claim the reviewer concern has been affirmatively resolved in the sense of robust detection.
