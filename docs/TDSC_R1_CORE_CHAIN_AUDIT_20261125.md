# TDSC-R1 P0: unprivileged online path / execution contract / post-attack recovery

## Scope and provenance

Base branch: `experiment/hydro-valve-cps-20261030` (SHA `88fee4d145e56752795652b7bd2f630fab83872d`). This addition **does not modify** the original 560-run IEEE39 data, checkpoint/holdout traces, the historical hydraulic SIL code or the submitted paper. It defines **new**, explicitly versioned SIL evidence. Its runtime is the existing two-valve `HydroPlant` with analytic controller updates, **not** a new IEEE39 MATLAB native simulation, a real PLC, a neural backbone, or a formal continuous-time CBF-QP proof.

## P0 audit findings (confirmed by code inspection)

1. `AEFCNativeController.m`: `cleanBelief` is used via `beliefDist` in online `risk`; `provenance(j)` reflects synthetic attacker identity and directly screens knowledge. The historical 560-run matrix is thus an *oracle-informed mechanism study*. `AEFCNativeCheckpointController.m` instead uses observable `norm(obsReceived-beliefNow)` in risk, but its physical trust boundary and sampled contract remain unverified.
2. The native shield applies `pinv(Bn)` with three iterations, not a certified robust CBF/CLF QP under validated state, disturbance and attack coverage.
3. The old hydraulic SIL `robust_shield` returns a backup with `shield_feasible=False` and `run_episode` executes it nonetheless; this fails execution-contract completeness.
4. Historical native IEEE39 main-study trajectories do not exit their recovery region or expose dangerous proposals; such episodes cannot measure physical return-to-recovery performance.

## New independent software experiment

`experiments/hydro_valve/run_tdsc_contract_chain.py` is **additive**. The simulator alone knows attack schedules and physical truth. `UnprivilegedController.decide(packet,memory)` receives only a bounded-noise local PLC observation, compromised HMI observation, client evidence, untrusted age claims and untrusted model updates. The offline true physical state, malicious client identities, attack schedule, and clean shadow never enter this method. A trusted local PLC channel and its error specification **are assumptions**, not cryptographically authenticated facts. This is not a privacy or secure hardware demonstration.

The execution supervisor computes a six-dimensional state uncertainty box from PLC-local telemetry and a declared noise budget. `interval_step` computes a **conservative enclosure** of the actual original discrete Euler plant dynamics under arbitrary downstream valve-command attacks in [-0.08,0.08] per channel and explicit inflow/load intervals. Hard safety bounds cover water head, both branch flows, turbine speed and valve positions, and the outgoing nominal valve command reserves attack authority. It checks monotone clamp, positive head and Euler coefficient assumptions. Every released command is certified, including a fallback; if the initial uncertainty box is uncovered, the model assumptions fail, search budget expires or no candidate is certified, release is **denied** and the simulation stops with an explicit failure. A finite candidate grid is not a globally optimal QP and cannot certify global infeasibility.

This is **sampled one-step** safety under the stated discrete model. It does not certify between-sample invariance, unknown actuator delays, physical PLC operation, full IEEE39 robust CBF/CLF behavior or independent observer validity. Coverage and true-state violations are independently assessed only in the simulation harness.

## Predeclared recovery protocol

- Four scenarios: clean, knowledge-only, physical-only, joint; default 10 matched seeds 240–249. 480 samples at 0.05 s; existing two-valve `HydroPlant`. Seed is statistical unit, not time sample.
- Attack interval: steps 120–239 inclusive. Physical attack biases HMI observations, applies a constant bounded post-shield valve-command offset of -0.08, and adds a temporary +0.010 load disturbance. The supervisor knows only attack/disturbance **bounds** (`qin` ±0.008 and `load` ±0.020), never the schedule or actual values. Knowledge poisoning changes the last of five untrusted clients' evidence and gradient updates.
- Recovery predicate `R`: each branch's true flow error ≤0.012 and true turbine-speed error ≤0.008, stricter than the physical safety box. To count an attack-recovery event, the physical state must be **outside** `R` at attack end, later enter and remain in `R` for **20 consecutive samples**. Not exposed ⇒ not a recovery event; no event before horizon ⇒ right-censored. A failed safety contract is reported separately.
- Each sample logs released command/status, gate and deployment acceptance, measured-state coverage, exogenous coverage, state safety, true recovery state, physical trajectory and certificate margin; truth is recorded **only** by the harness.
- The exploratory ten-seed run proves neither statistical superiority nor FedRL neural-backbone efficacy. Matched FedRL/RobustAgg methods under **the same safety interface and physical exposure** must be added for comparative claims.

## Reproducibility

```bash
python -m pip install numpy
python analysis/audit_tdsc_core_legacy.py
python -m unittest discover -s tests -p test_tdsc_contract_chain.py -v
python -m experiments.hydro_valve.run_tdsc_contract_chain --seed-start 240 --seeds 10 --output results/tdsc_core_chain_v1
```

GitHub Actions uploads manifest, summary and raw JSONL files including unfavorable outcomes. Never mutate historical frozen traces or change epsilon to manufacture correction.

## Open P0 issues

1. Implement a new **native IEEE39 MATLAB** online policy with the same explicit no-oracle packet boundary. Independently audit all call sites and train/deploy update paths; a new hydraulic SIL test does not retroactively fix the 560-run main results.
2. Integrate a certified sampled-data robust CBF/CLF solver or equivalent exact conservative counterpart into the *native* IEEE39 plant, including full-state coverage, solver timeout, independently verified backup and post-shield attacks.
3. Extend the new SIL to matched FedRL/RobustAgg and component ablations, and test an actual heterogeneous actor/critic shared backbone under the same protocol. The present script tests only analytic parameter updating.
4. Test compromised/stale metadata, adaptive low-and-slow attacks and loss of the trusted PLC/reference channel, distinguishing trusted assumptions from guaranteed system behavior.
