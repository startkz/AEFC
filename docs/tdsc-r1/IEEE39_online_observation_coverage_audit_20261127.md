# IEEE39 online-observation coverage audit

**Audit date:** 2026-11-27  
**Branch:** `experiment/tdsc-r1-ieee39-stress-recovery-20261125`

## Evidence sources

- Strict Bus16 fault pilot: GitHub Actions run [45920175235](https://github.com/startkz/AEFC/actions/runs/45920175235), four episodes, MATLAB R2024b.
- Complete Simscape Series registry: run [45920344894](https://github.com/startkz/AEFC/actions/runs/45920344894), audit result `PASS_OFFLINE_SERIES_REGISTRY_COMPLETENESS`.
- Independent repeat of the categorized inventory: run [45920180038](https://github.com/startkz/AEFC/actions/runs/45920180038).
- Causal four-channel mapping: `results/ieee39_r2024b/interface_mapping.json`.

## 1. Actual controller input coverage

The current `AEFCNativeController` receives **four locally tapped generator-speed channels**, not a full-grid measurement vector.

| Input | Generator | Native source signal | Corresponding controlled Pref path |
|---|---|---|---|
| 1 | Gen10@Bus30 | `Governor/w` | `Governor/Pref` to `Governor/Delta load setpoint` |
| 2 | Gen1@Bus39 | `Governor/w` | `Governor/Pref` to `Governor/Delta load setpoint` |
| 3 | Gen2@Bus31 | `Governor/w` | `Governor/Pref` to `Governor/Delta load setpoint` |
| 4 | Gen3@Bus32 | `Governor/w` | `Governor/Pref` to `Governor/Delta load setpoint` |

The mapping's `validated=true` status establishes a four-channel causal input/output correspondence: its 4-by-4 sensitivity matrix has rank 4 and condition number approximately 5.13. It does **not** establish sensor authentication, integrity, calibration error, or a trustworthy measurement-error bound. These four paths are local model signals; they must not be described as independently certified sensors.

## 2. Offline Simscape Series inventory

The complete v3 registry enumerated **19,355 unique valid Series paths**, with zero excluded leaves and no traversal truncation. Its capture interval was only **0–0.05 s**, so this run is a path/metadata inventory, not a fault-transient state trajectory.

| Category | Logged Series records | Interpretation |
|---|---:|---|
| Physical bus-voltage sections | 41 | Cover 39 logical buses, including split sections |
| Transmission-line phase currents | 102 | 34 lines × three phase-current channels |
| Transformer winding currents | 24 | 12 transformers × two winding-current channels |
| Rotor-angle candidates | 20 | Two logged paths per generator across 10 generators |
| Terminal-voltage candidates | 20 | Two logged paths per generator across 10 generators |
| Other Series leaves | 19,148 | Auxiliary, internal, duplicated and algebraic signals; not independent state dimensions |

The sample-count distribution in this inventory was:

- 12,048 leaves with four samples over 0–0.05 s;
- 7,100 leaves with 76 samples over 0–0.05 s.

The large number of logged leaves must not be interpreted as the dimension of the independent DAE state. Multiple leaves can be alternate representations, block inputs/outputs, algebraic quantities, or duplicated physical variables.

## 3. What the strict Bus16 pilot actually measured

The strict pilot recorded 481 samples from 0 to 8 s for all 41 bus-voltage sections and all 10 generator-speed monitors. It also retained the three phase-current trajectories for the adjacent B16–B17 line. The other 126 branch-current channels were retained as per-branch maxima over prefault, fault, and postfault windows, not as complete per-branch time-series files.

Across all four episodes:

- the original Bus16_1 fault was exposed under the preregistered recovery predicate;
- both methods first met the 20-sample recovery hold at 7.1833 s, approximately 2.0833 s after fault clearing;
- AEFC-Full accepted 470 internal adaptation updates per episode, but released zero execution corrections;
- the maximum added Pref correction was zero;
- AEFC-Full and Supervisor-only had identical paired physical traces.

Consequently, this experiment verifies strict refusal and the response of the original plant/governor system. It does not establish an AEFC physical recovery gain.

## 4. Unresolved certification premises

The current evidence explicitly leaves the following items unverified:

1. Trusted online sensor integrity and independent calibration/error bounds.
2. Complete dynamic and algebraic DAE state decomposition and dimension.
3. A verified measurement map from online observations to every safety-relevant state.
4. State-estimation error-set coverage under sensor faults, bias, delay and loss.
5. Sampled one-step reachable-tube coverage and continuous intersample reachability.
6. Validated thermal/current ratings and all bus/branch safety predicates.
7. Independent emergency-governor authority, feasibility, timeout behavior and backup viability.

The strict controller therefore remains fail-closed. The requirements document is not a certificate artifact; `fullstate_certificate_path` is intentionally empty until a reviewed certificate and its hash-verified model artifact exist.

## 5. Next implementation sequence

1. Extract and classify the native Simulink/Simscape dynamic states separately from the 19,355 logged Series leaves. Use block/state metadata and operating-point/state logging; do not infer state dimension from Series count.
2. Expand the measurement interface from four generator-speed paths to a reviewed set of safety-relevant measurements. Add explicit sensor models, sampling, quantization/noise, integrity assumptions and independently justified error bounds.
3. Map each measurement to the candidate state vector and verify observability/estimation error coverage under the preregistered sensor-fault model.
4. Derive and validate the sampled one-step reachable set and intersample tube against the native nonlinear DAE model.
5. Independently validate emergency-governor authority and fallback viability before enabling any added Pref correction.
6. Only after these gates pass, run the predeclared six-method recovery comparison. The currently running 32-case persistent-Pref pilot is exploratory four-speed-proxy evidence and cannot substitute for these certification steps.

**Claim boundary:** No complete IEEE39 state observability, full-network safety, continuous-time safety, backup viability, or AEFC full-network recovery gain is certified by the current runs.
