# IoT-J Fig. 5–6: 1000-episode raw convergence evidence protocol (2026-11-11)

## 1. Original manuscript and source authenticity

The user-provided manuscript \`main(20261111-012112).pdf\` labels Fig. 5
"Convergence of recovery time" (vertical axis "Recovery step") and Fig. 6
"Convergence of recovery accuracy" (%); both span 1000 episodes, showing
AEFC-FRL, MADDPG, FedRL, FedRL-NoAdv, FedRL-NoCW, and FedRL-OrdTopK.

**Do not represent the currently committed figure-generation scripts as
original simulator logs.** \`Figures/Convergence-Time.py\` and
\`Figures/Convergence-Accuracy.py\` generate synthetic noisy exponential
trajectories using a deterministic random generator. They do not read original
per-seed/per-episode restoration records, so regenerating those graphics is not
reproducing the claimed experiment. The earlier strict reproduction ledger
also explicitly says original Fig.5–13 raw source trajectories were missing.

The manuscript's Fig.5–6 source setting is the separate Simulink--Python
environment. The actual Simulink actor-critic experiment with all six
methods (particularly the full-information centralized MADDPG baseline)
is not currently a runnable, raw-trace-backed implementation in this branch.
No new IEEE39 AC experiment below is allowed to replace that source identity
or claim quantitative agreement with it.

## 2. Closest executable, scientifically valid supplementary study

Use the pre-existing \`iotj_bridge/strict_run.py\` IEEE39 **quasi-static
pandapower AC**, \`strict_agent.py\` learner, and unchanged 1000-episode
\`iotj-76369-full1000-core.yml\` hyperparameters. Add recording only:
\`--record-training-trace\`. No new reward, actor behavior, event, policy,
power-flow constraint, or federation timing is introduced.

- Case: IEEE39; N=5 heterogeneous clients (\`--hetero dim\`), clean run,
  actual M=0 malicious, no per-client cap.
- Training seeds: 80,81,82,83,84,85,86,87,88,89;
  1000 episodes/seed, each up to 30 AC steps, 200 aggregation rounds,
  10 held-out evaluations at the end.
- Local learner: PER, batch 256, hidden 128, latent 32,
  local critic/adapter steps 5, sharing steps 2, \`kappa=0.20\`.
- **No fixed traffic padding**: matches \`iotj-76369-full1000-core.yml\`.
- Four existing sharing rules and one newly identified dense credibility
  control: \`adv\` (AEFC-FRL), \`ordinary\` (FedRL-OrdTopK),
  \`adv_no_cw\` (FedRL-NoCW), \`dense\` (FedRL),
  \`dense_cw\` (FedRL-NoAdv: dense ordinary-loss sharing and existing
  utility--drift weighting). The new mode simply selects every replay
  sample and keeps all shared coordinates, using the same sharing optimizer.
- **MADDPG not included**: a joint-information centralized critic and
  original Simulink environment would have to be implemented and validated
  separately. No local-critic method may be relabeled "MADDPG".

All five AC methods are separate experimental control groups. They do NOT
assert reproduction of the full six-method native simulation.

## 3. Preserve raw episode and step evidence

For each \`(method,seed,episode)\`, archive:

\`episode\`, \`recovery_step\`, \`safe_dwell5\`, \`censored\`,
\`steps_executed\`, \`recovery_accuracy_pct\`, \`average_restored_pct\`,
\`final_restored_pct\`, \`max_thermal_excess_pct\`,
\`max_voltage_violation_pu\`, \`any_unsafe\`, \`client_outcomes\`,
plus **every actual step record** (\`t\`, \`restored_pct\`, \`safe\`,
\`ac_converged\`, voltage/thermal excess, bus/client values).

The *implemented* recovery predicate is first index of five **consecutive**
AC-converged steps having at least 90% served load and zero voltage and
thermal violations. If no such window occurs, \`recovery_step=-1\`,
\`censored=1\`. An unsuccessful episode is **not** assigned zero recovery
time, and a 31-step restricted score is reported separately from physically
observed time. Early failure on a nonconverged power flow remains recorded.

Recovery accuracy is terminal served load \`R_load\` in percent of demand.
It is **not** the fraction of episodes that recovered safely; \`safe_dwell5\`
reports that other endpoint. Hence the new recovery-time criterion should
not be silently equated with the unreported original Simulink Fig. 5
stopping rule.

Original raw output is a per-seed JSON, plus checkpoint \`.pt\`,
manifest with SHA-256 of both, full Git commit SHA, runtime/package
versions and test traces. Additional independent auditor:
\`iotj_bridge/audit_fig56_episode_traces.py\` checks each of 50 full-budget
trials, all 50,000 episodes, **recomputes** recovery steps and
accuracy directly from within-episode physical trace, and checks the
1000/200/10 budget, 90% five-safe-step criterion, censorship flags,
client count and protocol, CRC-like indices, emitted bytes and SHA-256.

## 4. Results and presentation rules

Never generate Fig. 5–6 from synthetic arrays or digitize image pixels
as though measured. The new independent audit emits:

- \`fig56_per_episode.csv\`: 50,000 unsmoothed seed–method–episode rows;
- \`fig56_per_step.csv.gz\`: 1.5 million or fewer actual step records;
- \`fig56_per_seed.csv\`: seed-level summaries;
- \`fig56_per_episode_seed_mean.csv\`: 1000 episodes × five real-method
  seed means, including number of censored seeds;
- \`fig56_seed_summary.csv\`: 10 independent-seed bootstrap 95% intervals;
- \`fig56_audit_report.json\`: pass/fail, hashes and explicit boundary;
- \`fig5_ieee39_ac_supplement.png\` and
  \`fig6_ieee39_ac_supplement.png\`: *supplementary* plots, labeled
  "IEEE39 quasi-static AC (not original Simulink figure)".
  Optional 31-episode moving average is solely visual; original raw
  episode data never smoothed or replaced. Zero is never imputed for
  unsuccessful recovery. Figure 5 supplement uses a **restricted recovery
  score** (failure encoded 31) with an explicit caption, not a mean
  conditional-on-success recovery time.

All confidence intervals aggregate training-seed summaries. Repeated
episodes and steps are dependent; counting them as independent
replications would be pseudoreplication.

## 5. Gate and manuscript disposition

Source, logs and audit are on the *separate* branch
\`experiment/iotj-fig56-episode-traces-20261111\`. The original R3
adaptive-attack artifacts and paper figures stay unchanged. If the full
matrix passes, only these new AC supplemental plots/tables and their
provenance may be described as measured. Fig. 5/6 in the uploaded
manuscript remain **native Simulink evidence not reproduced** until
matching native models and actual per-seed raw logs are supplied or
run. Any actual new native run must use the correct original methods,
stopping rule, actuator mapping, and 1000-episode protocol.
