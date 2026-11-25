# TDSC-R1 native IEEE39 P0 protocol: online privilege, execution contract and post-attack recovery

## Scope & frozen parent

Parent branch `audit/tdsc-r1-core-chain-20261125`, commit `1b0bdf6b66b67f7e560f2eae676da4ddd4a2d74f`. New branch `audit/tdsc-r1-ieee39-native-20261125`. Historic R2024b results `results/ieee39_joint20`, original baseline `experiments/matlab/aefc_ieee39_native_joint20.m` and the prior hydraulic SIL record remain untouched. The new branch modifies `AEFCNativeController.m` **on this branch only** to implement an online packet boundary and creates a new independent model `IEEE39BusSystem_AEFCUnpriv.slx` during CI.

### Security boundary

`AEFCNativeAttackHarness` exclusively receives `ScenarioCode`, `Seed` and `AttackScale` and creates a 67-field potentially compromised packet (4 HMI-like observations, 7 × 4 updates, 7 × 4 evidence reports, 7 report ages) together with a separate 4-channel downstream Pref attack signal. The harness has an input from the real native Simulink speed telemetry, but is not an online defender. Its internal attacker identity labels do not appear in the online packet. `AEFCNativeController.stepImpl` receives exactly (local trusted 4-rotor-speed telemetry, received 67-vector packet), and has no attack schedule, malicious client identity, scenario flag, offline clean shadow or `cleanBelief` access.

**Trust boundary:** the four local rotor-speed signals are assumed independently measured and not corrupted by the adversary. This assumption is not a full observer, no authenticated real-world PLC evidence, and no integrity proof for every other state component of the 39-bus power system. Age fields are visible metadata, *not* intrinsically authenticated; further adversarial manipulation must be separately tested.

### Native execution contract and its scope

The new `aefc_native_execution_contract` enforces hard inequalities over **only the observed four-speed affine surrogate** derived from the paired finite-difference sensitivity matrix `Bn`. For a proposed correction `u`, the condition is

```
 |z_local + Bn*u| + (sensor_budget + surrogate_model_residual)
     + abs(Bn)*post_shield_attack_upper <= normalized_safe_limit - reserve
 |u| <= action_limit - post_shield_attack_upper
```

An 11? no, 16-halfspace finite correction projection runs, followed by an exact direct inequality check. The candidate, fallback and null correction use **identical** proxy conditions across FedRL, RobustAgg, AEFC-Full and all included component ablations. Finite projection does **not** establish global infeasibility or optimality of a QP. `proxy_status>0` means the FOUR-CHANNEL surrogate check passed only; `full_state_coverage=0` and `full_state_certified=0` for every native IEEE39 trace. The local sensitivity residual and sensor bound in `configs/ieee39_unpriv_r1.json` are **unvalidated engineering allowances** rather than physical guarantees.

`ExploratoryMode=false` (strict) therefore withholds every additional injected Pref correction and logs rejection `proxy_status=-30` if proxy would pass. This does not deactivate or certify the already-existing internal native governor controllers. `ExploratoryMode=true` allows only surrogate-screened additional Pref corrections as diagnostic, with no full-state safety claim.

Separately, `aefc_native_full_state_contract` implements a genuine *conditional full-state linear robust hard-constraint counterpart*. Under independently verified complete state inclusion, affine discrete dynamics/uncertainty bounds and eligible actuator bounds, it enforces:

```
 mu = A*xhat + B*u + c
 sigma = |A|*e + |B|*a + w
 state_lower + sigma <= mu <= state_upper - sigma
 input_lower + a <= u <= input_upper - a
```

The system rejects uncovered states, unverified dynamics, infeasible input boxes or non-certifiable candidates. It is intentionally NOT connected to the native Simulink model: the **entire state trajectory**, its external observer and reachable tube are absent. The unit self-test runs 500 synthetic two-state affine points with an independent state sampler. This is not full IEEE39/continuous-time CBF/CLF certification.

### Experimental design

- Actual MathWorks R2024b native IEEE 39-bus model instrumented from the original official benchmark and the existing physical 4 x 4 rotor-speed/Pref mapping, not an external toy simulation.
- Distinct new experiment path `results/ieee39_unpriv_r1/<mode>` with commit, config hash, raw JSONL, summary and manifest, with explicit overwrite refusal.
- Methods under exactly the same last-stage surrogate checker: **AEFC-Full**, **Supervisor-only**, **RobustAgg**, **AEFC-no-PATBU**, **AEFC-no-Gate**, **AEFC-no-TGOPA**. The no-shield variant is purposely omitted from equal-supervisor comparisons.
- Scenario cells: clean, knowledge-only, physical-only and joint. Baseline scripted smoke tests 2 methods × 2 attacked conditions × 2 phase seeds; a separate pilot covers 6 methods × 4 scenarios × 5 seeds × 2 attack levels. No independent holdout will be chosen or tuned until pilot feasibility is known.
- The true rotor speed series is obtained only from the Simulink physical output. Recovery event: sample at attack end must be **outside** `max(abs(z_i))<=0.25` for 4 measured rotor-speed channels, *then* the state returns inside for 20 consecutive samples; if never exposed or if horizon ends, the event is not a success. Normalized observable safety threshold 1.0 is **four measured speeds only**, not full 39-bus safety.
- Native default uncertainty and post-shield budgets are frozen in a new separate config; `stop_time=3.0`, attack steps 15–89, post-shield attack `0.008 × scale` with maximum scale 3, envelope 0.024. No adaptive post hoc relaxation of recovery criteria; negative exposure/failed or censored episodes remain in the output.

### Execution & audit

```bash
python analysis/audit_ieee39_unprivileged.py
# MATLAB CI R2024b:
# addpath('matlab_r2024b');addpath('experiments/matlab');
# aefc_ieee39_bootstrap; aefc_ieee39_build_unprivileged;
# aefc_ieee39_unprivileged_joint('smoke');
# aefc_ieee39_unprivileged_joint('strict');
python analysis/audit_ieee39_unprivileged.py --results results/ieee39_unpriv_r1/smoke
```

The independent auditor verifies method/seed/scenario identity, all raw times and outputs, absence of full-state certification, post-shield attack bound, released-command proxy status, true four-speed envelope and strict attack-end outside→20-sample inside recovery definition. This is **not** an independent nonlinear state-coverage proof for Simulink.

### Non-negotiable P0 still open

1. Extract and validate a **full original IEEE39 dynamical physical state vector**, all safety predicates, sensor trust regions and conservative state-estimation error bounds for each seed and time.
2. Derive or verify a **bounded discrete full-state one-step transition** (and a separate hold-interval tube) under generator dynamics, network changes and post-shield perturbations. The 4 × 4 steady finite-difference speed/Pref Jacobian alone cannot provide this.
3. Integrate the full-state solver including time budget, certified backup feasibility and no-released-command emergency state. The current strict-mode null correction does not certify the underlying governor.
4. Only after a truly physically exposed experiment is established, compare same-supervisor methods and realistic hetero actor/critic FedRL with independent held-out seeds, matched physical states and baselines. Report control quality, admission/gate rates, risk boundaries and failures.
5. Reject any claim of formal IEEE39 CBF/CLF safety, globally optimal control, or full CPS resilient recovery based solely on this new four-speed experiment.

