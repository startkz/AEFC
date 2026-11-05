# IoT-J Dynamic IEEE39 Physical-Safety Evaluation Protocol (2026-11-05)

## Purpose

Extend the existing quasi-static pandapower IEEE39/118 evidence with a separately versioned dynamic evaluation on the native MathWorks `IEEE39BusSystem` Simscape Electrical model (MATLAB R2024b). The dynamic study is intended to measure quantities that the AC power-flow experiment cannot provide: generator rotor-speed-derived frequency response, RoCoF, governor/actuator response, and protection events.

This protocol does not replace or relabel the existing AC results. It also does not treat the legacy `AEFCNativeController` (PATBU/Gate pipeline) as the IoT-J AEFC-FRL learner. Any native-controller calibration run is reported only as a plant/instrumentation check. Publication-facing AEFC-FRL dynamic claims require the manuscript-aligned local-critic/shared-actor-backbone learner to be integrated with the dynamic plant and rerun under the same protocol.

## Verified starting point

- Native model: MathWorks `IEEE39BusSystem`, R2024b, Simscape Electrical.
- Existing model bootstrap and 0.2-s smoke run succeeded.
- Four generator-local Pref control edges and four paired rotor-speed observation edges were causally probed; the measured 4x4 sensitivity matrix had rank 4 and condition number 5.129638.
- The official example includes ten generators with AVR, exciters, PSS, governors and prime movers. Its documented disturbance is a three-phase-to-ground fault at Bus 16 at 5.0 s, cleared after 0.1 s.
- The existing `configs/ieee39_joint20.json` uses StopTime=1.20 s, so that earlier matrix does not include the documented 5.0-s fault and cannot be used as dynamic fault-response evidence.

## Phase A — dynamic instrumentation qualification

1. Load the official MathWorks model without changing its network or protection/fault settings.
2. Discover all ten generator-governor rotor-speed outputs and branch each to an explicit To Workspace sink.
3. Inventory governor Pref, prime-mover/mechanical-power, valve/gate/servo, load, breaker, switch and fault blocks. Record block paths, types, mask metadata, and output connections.
4. Run the documented Bus-16 fault through 20 s using the native governor controls.
5. Preserve raw per-generator rotor-speed traces, derive local frequency as (f_i=60omega_i) Hz (the initial measured speed is approximately 1 p.u.), and calculate per-machine frequency deviation and RoCoF.
6. Extract inertia and machine-rating parameters from the actual model before computing an inertia-weighted COI frequency. If those parameters cannot be unambiguously read, report per-generator rotor-frequency metrics only; do not substitute an unweighted average and call it COI frequency.
7. Treat this run as baseline/instrumentation qualification, not as an AEFC-FRL method comparison.

## Phase B — actuator and protection integration

- Preserve the four causally validated Pref channels as candidate control interfaces.
- Identify and tap the actual governor actuator state and mechanical-power output. Do not use Pref alone as a proxy for physical actuator motion.
- Apply explicit command-amplitude and command-rate limits at the control interface, while retaining the native governor/prime-mover dynamics. Record raw request, limited request, actuator state, mechanical power, saturation state, and measured slew rate for each channel.
- Inventory native breaker/load interfaces before adding protection. If the model contains no applicable load breaker, add a physically connected three-phase breaker at a documented load feeder; do not log a software trip flag as an executed protection action.
- Implement staged under-frequency load shedding only after the breaker interface and frequency signal are validated. Freeze thresholds, delays, hysteresis, and shed fractions before method comparison.

## Required metrics

### Frequency
- Per-generator (f_i(t)), (Delta f_i(t)), nadir, peak, and settling time.
- Per-generator maximum absolute RoCoF, computed from a documented finite-window slope estimator.
- COI frequency and RoCoF only when actual inertia and rating weights are extracted and audited.
- Fault onset and clearing timestamps.

### Actuator
- Raw and limited Pref commands.
- Actual governor actuator/valve/gate signal, where exposed by the model.
- Mechanical power (P_m(t)).
- Command amplitude and slew-rate maxima; time and count of amplitude/rate saturation; tracking error and actuator lag.

### Protection
- Relay pickup time, trip decision time, breaker command time, actual breaker state transition, shed MW and percentage of pre-fault load.
- Protection stage, threshold, timer, reset/hysteresis state, and post-action frequency response.
- Distinguish the documented fault-clearing event from a protection relay operation.

## Phase C — manuscript-aligned learning evaluation

The dynamic plant run must use the IoT-J learner in `iotj_bridge/strict_agent.py` (or a versioned, audited adapter preserving its actor/critic, local adapters, shared backbone, advantage-conditioned sparse sharing, prototype alignment, and server aggregation). The legacy MATLAB PATBU/Gate controller is not a substitute.

Use four agents only if each is explicitly paired with one of the four validated governor Pref interfaces; otherwise retain the manuscript's client count and define a validated allocation from clients to physical actuators. State the resulting client/actuator mapping and compromised-client ratio.

Use independent training seeds and held-out evaluation seeds. Keep the disturbance, fault clearing, actuator limits, protection thresholds, rewards, observation transforms, and method configurations identical across methods. Report all failed or censored runs. Do not mix the dynamic 20-s protocol with the existing 1.2-s native matrix or quasi-static pandapower metrics.

## Evidence gates

- G1: ten rotor-speed traces are present, finite, time-aligned, and begin near the steady-state operating point.
- G2: the documented 5.0-s fault and 5.1-s clearing are visible in the raw model event/trace.
- G3: COI weights are extracted from the actual machine parameters or COI is omitted.
- G4: actual actuator output and mechanical power signals are identified and causally checked.
- G5: protection action changes a physical breaker state and the resulting shed load is measured.
- G6: the full IoT-J learner—not a legacy controller or a replayed open-loop action trace—is connected for publication-facing method comparison.
- G7: raw traces, model revision, MATLAB release, resolved parameters, configs, and SHA256 manifests are archived.

A successful MATLAB workflow alone is not a scientific pass. Phase A only qualifies the dynamic measurement path; Phases B and C remain open until their respective evidence gates pass.
