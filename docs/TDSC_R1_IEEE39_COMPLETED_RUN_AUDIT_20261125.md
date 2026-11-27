# TDSC-R1 IEEE39 completed remote-run audit — 2026-11-25

## Executive decision

**The latest 360 native IEEE39 stress episodes do not demonstrate physical outside-to-recovery gain and do not certify complete IEEE39 safety.** They do show a small in-set ten-generator rotor-speed-envelope response difference for the current four-dimensional AEFC heuristic prototype versus Supervisor-only. The trained federated-RL checkpoint is absent. A separate, earlier 180-episode checkpoint experiment did demonstrate a parameter-space rollback to a local pre-attack checkpoint in 19/20 eligible seeds per attacked scenario, but it did not demonstrate physical system recovery and incurred higher physical response cost.

Keep PR #15 in Draft and keep the full-network safety/paper-promotion gate BLOCKED.

## 1. Completed 360-episode native IEEE39 experiment

Source: [GitHub Actions run 45547490002](https://github.com/startkz/AEFC/actions/runs/45547490002), audit artifact `ten_seed_sixmethod_physical_audit.json`, and independent raw JSONL re-audit.

| Item | Audited result |
|---|---:|
| Native episodes | 360 |
| Methods | 6 |
| Independent paired seeds | 10 (80–89) |
| Physical/joint attack conditions | 2 |
| Exploratory held Pref amplitudes | 0.06, 0.12, 0.24 p.u. |
| Recorded samples | 65,160 |
| Attack-active samples | 27,000 |
| Raw solver-time ten-speed samples | 65,160 |
| Maximum normalized ten-generator speed deviation | 0.224561 |
| Maximum at last attacked sample | 0.153989 |
| Attack-end outside-recovery events | **0** |
| Genuine 20-sample outside-to-inside recoveries | **0** |
| Ten-speed sampled proxy-bound violations | 0 |
| Raw solver-time ten-speed proxy-bound violations | 0 |
| Maximum Pref accounting residual | 1.67e-16 |

The recovery set was fixed at `max_i |(omega_i(t)-omega_i(0))/0.02| <= 0.25`; an episode was eligible only if it was outside at the final attacked sample. The largest normalized ten-generator speed deviation anywhere in the 3 s episode was 0.224561, below 0.25. At the final attacked sample the largest value was 0.153989. Thus no episode qualified for a recovery-time or recovery-rate comparison. The zero violation result applies only to the ten logged rotor-speed channels and the unvalidated proxy limit; it is not a full-grid safety result or a continuous reachable-tube proof.

All 360 main-study pressure amplitudes exceed the earlier 0.024 p.u. original post-shield attack bound. They are a separately labelled exploratory stress envelope, not evidence under the original certified attack contract. The attack was applied downstream of the four Pref correction paths. The measured identity `delivered Pref = original governor Pref + shield correction + attack` held to a maximum residual of 1.67e-16.

### 1.1 In-set response metric (not recovery)

The audit metric is the time-average of the maximum absolute normalized speed deviation across the ten generators, then averaged over six matched conditions per independent seed. Lower is better.

| Method | Mean over 10 seed-level means |
|---|---:|
| Supervisor-only | 0.048935 |
| AEFC-Full | 0.045577 |
| AEFC-no-PATBU | 0.047035 |
| AEFC-no-Gate | 0.045577 |
| AEFC-no-TGOPA | 0.045405 |
| RobustAgg | 0.045384 |

For AEFC-Full versus Supervisor-only, the paired seed-level difference (Supervisor-only minus AEFC-Full) is 0.003359, with a 95% seed-level t interval [0.002511, 0.004206], exact two-sided sign-test p=0.001953, and positive difference for 10/10 seed means. The independent seed-cluster bootstrap in the original audit reports [0.002669, 0.004038]. This is approximately a 6.86% reduction in the stated in-set speed-envelope metric. It is not a post-fault recovery gain.

Across the 60 pressure/scenario/seed paired conditions, AEFC-Full improved this metric in 50 and was worse in 10. The two-seed pilot was not consistent: its aggregate paired difference was 0.000102 with interval [−0.000289, 0.000493].

### 1.2 Gate ablation is inactive in this experiment

The raw trace audit found:

- AEFC-Full gate closures: **0 / 10,860** samples.
- AEFC-no-Gate gate closures: **0 / 10,860** samples.
- The checked Full and no-Gate raw trajectories are identical in every field except the method label.
- AEFC-Full deployed updates were accepted at all 10,860 samples.

Therefore, this experiment provides no empirical evidence for the independent contribution of the Gate. The no-Gate ablation did not activate a distinct execution path under the tested conditions. Do not claim Gate-specific benefit from this result.

AEFC-Full also has a small but measurable advantage over no-PATBU on the in-set speed metric (seed-level difference 0.001458; 95% t interval [0.000743, 0.002173]; 10/10 positive seed means). RobustAgg and no-TGOPA have slightly lower mean values than AEFC-Full, with no demonstrated significant Full advantage over those alternatives.

### 1.3 Proxy execution details

The six-method run recorded 65,160 positive proxy-release statuses and zero refusals. The Full method's proxy intervention was nonzero in 6,389/10,860 samples, but its gate never closed. The proxy bounds are explicitly marked unvalidated, and the controller has only four online speed inputs. These counts do not establish all-bus, branch, governor, or DAE safety.

## 2. Other completed runs

### 2.1 32-episode Pref pilot

[Actions run 45547174284](https://github.com/startkz/AEFC/actions/runs/45547174284)

- 32 episodes, 5,792 sampled records, 2,400 attacked samples.
- Maximum ten-generator normalized speed deviation: 0.169514.
- Zero attack-end exposures and zero true recoveries.
- Two independent seeds only; paired response difference 0.000102 with interval [−0.000289, 0.000493]. Exploratory only.

### 2.2 24-episode strict refusal fallback

[Actions run 45547120208](https://github.com/startkz/AEFC/actions/runs/45547120208)

- 24 native episodes and 4,344 sampled records.
- Additional Pref correction refused at all 4,344 samples.
- Zero sampled ten-speed proxy violations, zero attack-end exposures and zero true recoveries.
- This confirms fail-closed behavior for the added correction path under these tests. It does not certify the original governor or full IEEE39 network.

### 2.3 Statistical self-tests

[Actions run 45547639270](https://github.com/startkz/AEFC/actions/runs/45547639270) passed synthetic tests for the distinction between prevention and recovery, right-censoring, and insufficient independent seed counts. These are tests of analysis semantics, not physical plant results.

## 3. Method identity

[Method-fidelity audit run 45547302648](https://github.com/startkz/AEFC/actions/runs/45547302648) passed its fail-closed integrity check.

The current native MATLAB controller is a four-dimensional heuristic adaptation. Its online client updates and evidence are generated from normalized rotor-speed observations with deterministic perturbations. There is no trained neural/federated-RL policy checkpoint loaded by this stress runner. The native physical response experiment therefore supports, at most, a mechanism-prototype result—not an end-to-end trained AEFC-FRL algorithm claim.

## 4. Separate historical parameter-checkpoint experiment

This is a distinct experiment and must not be merged into the 360-episode physical-recovery denominator.

- Native run [39555085441](https://github.com/startkz/AEFC/actions/runs/39555085441) and independent audit/persistence run [39559082604](https://github.com/startkz/AEFC/actions/runs/39559082604) succeeded.
- 180 episodes, 39,600 samples, 20 held-out seeds per scenario/method.
- Under knowledge-only and joint attacks, the checkpoint detector alarmed in 20/20 seeds per scenario; clean false alarms were 0/20.
- AEFC-Checkpoint reached the local checkpoint `epsilon=0.001`/20-hold criterion in 20/20 seeds per attacked scenario; 19/20 were genuine post-attack outside-to-inside parameter corrections, while one seed was already inside tolerance at the attack-stop sample.
- The restored object was the four-dimensional `theta` vector, not the physical grid state and not a neural policy backbone. The local commissioning checkpoint was assumed intact; it was not cryptographically attested.
- The checkpoint method's final dynamic clean-shadow error increased to 0.064342 (knowledge) / 0.064538 (joint), compared with 0.010483 / 0.010420 for Unprivileged. Mean normalized physical response L1 increased to 0.034609 / 0.034712 from 0.019272 / 0.019767. Post-attack deployment acceptance was zero over 176 samples. This is a parameter rollback/degraded-survival result with an adaptation and physical-response cost—not proof of improved physical recovery.

## 5. Full-grid safety evidence and diagnostic defects

### 5.1 Existing full-state gate

The machine-readable requirements in `configs/ieee39_fullstate_certification_requirements.json` remain unsatisfied: complete rotor-angle, bus-voltage, branch-flow/thermal, actuator/governor bounds; trusted full-state observer coverage and error set; full nonlinear/DAE sampled and intersample reachable tubes; and verified emergency governor viability are absent. The promotion gate must remain BLOCKED.

### 5.2 Simscape census v1 misclassified logged leaves

[Actions run 45547363931](https://github.com/startkz/AEFC/actions/runs/45547363931) successfully logged 17,170 original Simscape leaf series, but the v1 parser looked at the child name `series` instead of the parent variable path. Its reported zero voltage/current candidate counts are a parser defect, not evidence that the model lacks those variables. Independent inspection of the archived 12,000 captured paths found 39 logical Bus IDs with `Vt` series, 41 physical bus sections (Bus16 and Bus26 are split into two sections), bus current series, and line/transformer current and loss series. The captured v1 inventory was truncated, so corrected v2 extraction is required. These are offline simulator-oracle logs, not trusted online sensors.

### 5.3 Physical disturbance inventory v1 was only candidate discovery

[Actions run 45547985794](https://github.com/startkz/AEFC/actions/runs/45547985794) scanned 9,102 blocks. Its 40 “grid load” candidates were ConnectionLabel/LoadLabel blocks, not validated physical load injection ports. It identified one actual `Fault (Three-Phase)` block, whose parameters and wiring require inspection before it can be used as a validated disturbance.

### 5.4 Four-input observability workflow v3 failed on an artifact-path mismatch

[Actions run 45547038939](https://github.com/startkz/AEFC/actions/runs/45547038939) executed the MATLAB linearization command but failed in the following audit step because the script wrote `native_local_observability_probe_v2.json` while the workflow expected `native_local_observability_probe_v3.json`. MATLAB also emitted square-root-of-negative warnings. The failed workflow is not a negative observability-rank result; the actual output was not archived. The corrected v4 run is required before interpreting local rank.

## 6. Follow-up diagnostics now submitted

- Corrected four-input local observability output path: [run 45572989915](https://github.com/startkz/AEFC/actions/runs/45572989915).
- Corrected Simscape series parent-path parsing and offline Bus Vt/branch-current value extraction: [run 45573074276](https://github.com/startkz/AEFC/actions/runs/45573074276).
- Actual Three-Phase Fault/load/line/transformer mask and wiring inventory: [run 45573167493](https://github.com/startkz/AEFC/actions/runs/45573167493).

These diagnostics were still running at the time of this audit; their outputs must be reviewed before designing the next physical-fault experiment.

## 7. Publication decision

Do not claim complete IEEE39 safety or an independent physical AEFC recovery gain from the latest 360 episodes. The supported statement is:

> On the tested native IEEE39 exploratory Pref-stress conditions, the current four-dimensional heuristic AEFC mechanism prototype reduced the in-set ten-generator speed-envelope metric relative to Supervisor-only across the ten seed-level averages. No episode crossed the preregistered attack-end recovery-set boundary, so the experiment did not yield a physical outside-to-recovery event. The experiment did not certify full IEEE39 bus/branch/DAE safety or evaluate a trained federated-RL policy checkpoint.

Retain all failed, non-exposed, and censored outcomes. Do not lower the recovery threshold or redefine the attack-stop criterion after observing these results.


## 8. Post-audit native physical diagnostics — 2026-11-25

### 8.1 Corrected full-grid offline Simscape current census

[Grid Census v5](https://github.com/startkz/AEFC/actions/runs/45582393099) completed successfully. It traversed 22,413 Simscape nodes and 19,355 logged leaves without truncation and confirmed:

| Native offline quantity | Result |
|---|---:|
| Logical bus voltage channels | 39 |
| Physical bus voltage sections | 41 |
| Transmission-line components | 34 |
| Line inductor current-amplitude series | 102 |
| Transformer components | 12 |
| Transformer winding-current series | 24 |
| Total selected branch-current series | 126 |

The line channels are the original `transmission_line/inductor_{a,b,c}/i/amplitude` series; transformer channels are `i1` and `i2`. All are finite and carry amperes as their unit. This census establishes offline simulator-log coverage only. It does not establish online sensor trust, thermal ratings, branch-limit margins, or DAE safety.

**Interpretation caveat:** the captured `inductor_a` current-amplitude values are near numerical zero across the inspected branches, whereas `inductor_b` and `inductor_c` are nonzero. Do not silently interpret all three labels as validated physical phase-current channels. The current mapping is retained for follow-up inspection of the native line subsystem and its phase convention. The branch-current channels are not used in the preregistered recovery predicate.

### 8.2 Original three-phase fault location resolved

The original masked block is `IEEE39BusSystem/Grid/Fault (Three-Phase)`, with the frozen native settings: ABC fault variant, fault type option 11, (R_{pn}=R_{ng}=10^{-3} Omega), temporal fault enabled, start at 5.0 s, and duration 0.1 s.

Two independent native-connection diagnostics succeeded:

- [Fault parent/child line-segment mapping v5](https://github.com/startkz/AEFC/actions/runs/45582643023)
- [Fault PortConnectivity endpoint mapping v6](https://github.com/startkz/AEFC/actions/runs/45582793472)

Both resolve the fault's physical connection to **Bus16_1**, the split physical section of logical Bus 16, and the adjacent native transmission-line block **B16 to B17**. This is based on the original port handles and physical line-segment endpoints, not on block-name inference. The fault location is now suitable for a location-specific physical-recovery study.

### 8.3 Pilot and local-observability implementation failures

[Fault pilot v3](https://github.com/startkz/AEFC/actions/runs/45582496284) reached the MATLAB execution stage but stopped before simulation because `SimulationInput.setBlockParameter` was called with multiple parameter pairs in one call. MATLAB requires one parameter/value pair per call. This is an API-use defect, not a negative physical result. Pilot v4 separates the calls and is the current rerun.

[Local observability v7](https://github.com/startkz/AEFC/actions/runs/45582398071) successfully entered the linearization stage but rejected the Goto-block input as an invalid linearization I/O point. The per-time attempts were recorded as `NATIVE_LINEARIZATION_FAILED`; this is not evidence of physical unobservability. The revised v9 probe places the four-dimensional input point on the nonvirtual `AEFC_NATIVE_CONTROLLER` action output and separately observes the actual four online speed channels and ten offline generator-speed channels.

The actual four online measurements are the rotor-speed outputs of `Gen10@Bus30`, `Gen1@Bus39`, `Gen2@Bus31`, and `Gen3@Bus32`, as specified in the validated `interface_mapping.json`. The ten-generator output is retained only as an offline upper-bound diagnostic.

### 8.4 Current experimental status and publication boundary

- The 360-episode exploratory Pref-stress result remains the only completed ten-seed physical-response comparison. It had no attack-end outside-recovery events.
- The 180-episode historical checkpoint experiment remains a parameter rollback result, not a physical-state recovery result.
- The native Bus16_1 fault pilot is still a two-seed exploratory test; it must establish actual recovery-set exposure before a ten-seed confirmatory run is justified.
- The full-network safety gate remains **BLOCKED**. No current run verifies trusted online full-state observation, validated branch thermal limits, nonlinear DAE reachable tubes, or continuous intersample safety.
- Do not change the preregistered 5% bus-voltage tolerance, normalized ten-generator speed bound, 20-sample hold, fault window, or right-censoring rule after observing the pilot.


### 8.5 Local four-sensor observability and four-action controllability results

[Local observability v9](https://github.com/startkz/AEFC/actions/runs/45583683445) completed successfully at two prefault operating points (0.10 s and 0.35 s). The linearized model has 285 states, four action inputs, four actual online speed outputs, and ten offline generator-speed outputs. The four online measurements are Gen10@Bus30, Gen1@Bus39, Gen2@Bus31, and Gen3@Bus32.

| Local diagnostic | 0.10 s | 0.35 s |
|---|---:|---:|
| Four-online-speed observability rank (machine precision) | 112/285 | 113/285 |
| Ten-offline-speed observability rank (machine precision) | 139/285 | 140/285 |
| Four-action controllability rank (machine precision) | 72/285 | 72/285 |
| Four-online-speed rank at relative tolerance (10^{-8}) | 80/285 | 80/285 |
| Ten-offline-speed rank at relative tolerance (10^{-8}) | 135/285 | 135/285 |
| Four-action controllability rank at relative tolerance (10^{-8}) | 36/285 | 36/285 |

The additional six offline speed channels increase the local numerical observability rank, but neither four nor ten speed outputs make the 285-state linearized model fully observable. The four Pref correction actions likewise do not make the full state controllable.

The singular spectra are severely ill-conditioned: observed condition numbers are approximately (10^{40})–(10^{43}) for observability and (10^{35}) for controllability. Therefore, the machine-precision ranks are tolerance-sensitive numerical diagnostics, not robust structural-rank claims. At a relative (10^{-8}) threshold, the effective ranks are materially lower. The reproducible threshold audit is stored in `results/ieee39_safety_mapping/local_rank_spectrum_audit_v9.json`; the raw MATLAB matrices are archived in the v9 workflow artifact.

This evidence supports a limited conclusion: the present four-generator measurement set and four Pref action channels expose only partial local state information and actuation authority. It does **not** prove global nonlinear/DAE unobservability, nor does it establish safety. It does, however, rule out treating the current four-speed observation vector as a full-state measurement.

### 8.6 Fault-pilot v4 failure and corrected v5 rerun

[Fault pilot v4](https://github.com/startkz/AEFC/actions/runs/45583843924) reached the MATLAB execution stage but failed before simulation because the script attempted to change `SimscapeLogName` through `SimulationInput` after enabling Fast Restart. MATLAB prohibits this parameter change while the model is initialized in Fast Restart. This is another execution-configuration failure, not a physical fault or recovery result.

Pilot v5 configures `SimscapeLogType` and `SimscapeLogName` once before enabling Fast Restart, preserves the four actual online observations in every JSONL record, and records the verified Bus16_1/B16-to-B17 location in the run manifest. The v5 run is the current physical-fault pilot; no recovery result should be claimed until its artifact is audited.


### 8.7 Busbar-port current channels recovered

[Grid Census v6](https://github.com/startkz/AEFC/actions/runs/45584829568) completed successfully after replacing the escaped-digit expression with an explicit digit class in the native Simscape path parser. It now extracts 123 busbar-port current series in addition to the 39 logical-bus voltage channels and 41 physical voltage sections. Each busbar current series is reported in amperes with a three-component dimension `[1,3]`.

For the faulted physical section, the original model exposes `Bus16_1/I1` through `Bus16_1/I4`. The physical-connection audit independently maps `Bus16_1/RConn1` to `B16 to B17/LConn1`. The current-channel-to-port index association is retained as a candidate mapping pending a complete all-bus port-to-component reconciliation; do not yet treat every `I#` label as a validated branch identity.

The updated complete offline census therefore contains 39 logical bus voltage channels, 41 physical bus voltage sections, 123 busbar-port current series, 102 line-inductor current-amplitude series, and 24 transformer winding-current series. These remain simulator-oracle records, not online trusted sensors or certified thermal measurements.


## 9. 2026-11-27 addendum — Bus16 fault, strict refusal, and full port topology

This addendum supersedes the earlier status statements in Sections 8.4 and 8.6 that described the Bus16 fault pilot as still awaiting physical-artifact review. It does not alter the historical 360-episode exploratory Pref-stress result or the earlier 48-episode non-exposure result.

### 9.1 Latest Bus16_1 strict fault pilot

The corrected strict rerun [Actions run 45921838661](https://github.com/startkz/AEFC/actions/runs/45921838661) completed successfully and its archived artifact was independently inspected.

The four pilot episodes (two methods × seeds 0 and 1) use the original native Bus16_1 three-phase fault at 5.0–5.1 s. The fault produces a maximum Bus16-section relative voltage deviation of approximately 0.999944 and a maximum ten-generator normalized speed deviation of 0.446705. The adjacent B16–B17 line current reaches approximately 7.115 kA in the fault window; the recorded fault-current maximum is approximately 18.136 kA. These are simulator-observed currents, not validated thermal-limit comparisons.

All four episodes first satisfy the frozen 20-sample recovery predicate at 7.1833 s, approximately 2.0833 s after clearing. The strict gate reports zero added Pref correction, zero execution releases, and zero backup actions. AEFC-Full records 470 accepted internal adaptation samples per episode, but none is released to the plant. The paired AEFC-Full and Supervisor-only bus-voltage, ten-speed, adjacent-line-current, original-Pref, and delivered-Pref traces are pointwise identical. The physical trajectories for seeds 0 and 1 are also pointwise identical.

**Interpretation:** the pilot satisfies the exposure prerequisite and demonstrates strict refusal while the original plant/governor response returns to the sampled recovery set. It does not demonstrate an AEFC physical recovery gain or certify the original Governor's robust viability.

### 9.2 Ten-seed confirmatory replay

The preregistered seed-80–89 replay is running at [Actions run 45924335524](https://github.com/startkz/AEFC/actions/runs/45924335524). It retains the same fault, methods, thresholds, sampling and 20-point hold. The controller seed changes offline client-packet generation; it does not inject a seed-driven physical disturbance. The post-run audit therefore explicitly distinguishes reproducibility from independent physical sampling. No inferential physical-effect claim is authorized merely by completing 20 episodes.

### 9.3 Separate 32-case persistent-Pref pilot

[Actions run 45920180021](https://github.com/startkz/AEFC/actions/runs/45920180021) completed 32 exploratory episodes over Pref stress amplitudes 0.024, 0.06, 0.12 and 0.24. The largest observed ten-generator normalized speed deviation was approximately 0.169514, below the frozen 0.25 recovery-set boundary. There were zero attack-end exposures and zero true recovery events. This experiment is not a recovery-time comparison; the amplitude range must not be enlarged post hoc and merged into the original preregistered protocol.

### 9.4 Structural mapping of all 123 busbar ports

[Actions run 45772532158](https://github.com/startkz/AEFC/actions/runs/45772532158) successfully resolved all 123 physical busbar ports using parent/child physical connection-line handles: 123 matched, zero unresolved, 34 unique line blocks, and 12 unique transformer blocks across 41 busbar sections. The map also identifies load, generator, fault, and split-bus interconnections. Five busbar ports have multiple connected component endpoints, including the Bus16/Bus26 split sections and Bus16_1/RConn1's connection to both B16–B17 and the three-phase fault.

The map deliberately leaves the Simscape I# current-variable-to-LConn/RConn association unvalidated. A separate raw current/port capture is running at [Actions run 45924972310](https://github.com/startkz/AEFC/actions/runs/45924972310), with 123 bus-port current series, 126 selected line/transformer current series, and model connectivity metadata. The known near-zero inductor_a/i/amplitude series remain a phase-mapping/model diagnostic; they must not be reported as validated nonzero phase currents without further checks.

### 9.5 Publication boundary

The Bus16 pilot can support a fail-closed execution statement and an observed original-plant post-fault response statement. It cannot support AEFC recovery superiority. The 32-case Pref pilot cannot support physical recovery because it never leaves the recovery set. The 123-port topology map supports offline structural connectivity, not authenticated online measurements. The full IEEE39 certification gate therefore remains **BLOCKED** pending trusted measurement/error bounds, validated current/thermal mappings, complete DAE coverage, sampled and intersample reachability, and independently verified backup-governor viability.
