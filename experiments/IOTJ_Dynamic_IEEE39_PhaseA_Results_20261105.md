# IoT-J Dynamic IEEE39 — Phase A Results (2026-11-05)

## Provenance

- Workflow: [IoTJ native IEEE39 dynamic frequency instrumentation](https://github.com/startkz/AEFC/actions/runs/41967607726)
- Run ID: `41967607726`
- Source commit: `b3a688f429452050a7fd96b47c58207a11b03a42`
- Branch: `experiment/iotj-dynamic-ieee39-20261105`
- Model: MathWorks `IEEE39BusSystem`, MATLAB R2024b, Simscape Electrical
- Stop time: 20 s; 1201 aligned samples; median sample interval 1/60 s
- Disturbance: native Bus-16 three-phase fault, start 5.0 s, duration 0.1 s, scheduled clear 5.1 s

## Frequency reconstruction

All ten generator-governor rotor-speed traces were recorded. The inertia-weighted COI frequency was computed using the actual `H` and `SRated` values read from the ten native `Machine Mechanical Power` blocks:

```
f_i(t) = 60 * w_i(t)
f_COI(t) = sum_i(H_i * S_i * f_i(t)) / sum_i(H_i * S_i)
```

The total `sum(H_i*S_i)` from the native model is 78,269.99 MW·s. Gen1@Bus39 contributes 63.88% of this inertia weight, so the COI metric must be interpreted alongside the individual generator rotor-speed traces.

| Metric | Measured value |
|---|---:|
| Pre-fault COI mean (4–5 s) | 59.979185 Hz |
| Maximum COI frequency after fault | 60.187177 Hz at 5.516667 s |
| Positive COI excursion from pre-fault mean | +0.207992 Hz |
| COI minimum during 5.1–10 s | 59.984183 Hz |
| Maximum absolute COI RoCoF | 1.267047 Hz/s at 5.066667 s |
| COI settling time after fault clear | 1.083333 s |

The worst local rotor-frequency nadir is 59.602025 Hz at Gen5@Bus34 (5.966667 s), a 0.377149 Hz drop from that machine's pre-fault mean. The highest local rotor-frequency peak is 60.553813 Hz at Gen4@Bus33. The largest local 100-ms-smoothed RoCoF is 5.095705 Hz/s at Gen4@Bus33.

RoCoF is calculated from the sampled rotor-speed-derived frequency using a numerical gradient followed by a centered six-sample (0.1 s) moving mean. These are rotor-speed-derived frequencies and an inertia-weighted COI frequency, not terminal-bus PMU readings.

## Important interpretation

1. The Bus-16 fault produces a positive COI frequency excursion and spatially heterogeneous rotor-speed oscillations; it is not a sustained underfrequency event.
2. The native model's fault clearing is timer-driven by the fault block's `fault_start_time=5` and `fault_duration=0.1` parameters. This is not evidence of a relay operation.
3. The unmodified model inventory contains no relay or circuit-breaker blocks.
4. The run is a dynamic measurement qualification and deterministic plant baseline. It is not an AEFC-FRL policy comparison and has no seed-level statistical inference.
5. The existing 1.20-s native matrix does not reach the 5.0-s fault and must not be cited as a dynamic fault-response experiment.

## Phase B evidence now being collected

The next workflow records, for the four validated generator-local Pref channels:

- raw Pref test request;
- rate-limited and amplitude-limited Pref correction;
- actual Pref signal;
- governor `delta_y` output (governor actuator state);
- non-reheat turbine `Tm` output (per-unit mechanical torque);
- local rotor speed and derived mechanical power `Tm*w`;
- native governor/turbine saturation parameters and fault-block external-control/measurement-port metadata.

The Phase-B calibration uses a deterministic test pulse. It is a plant-interface qualification, not an AEFC-FRL policy result. A publication-facing dynamic learner comparison remains a separate gate.
