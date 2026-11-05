# IEEE 39-bus dynamic transient experiment

This experiment is separate from the pandapower AC quasi-static runs.

## Model

The workflow uses the maintained IEEE 39-bus New England example distributed with a pinned PowerDynamics.jl source revision. It includes 39 buses, 46 branches, 10 synchronous machines, sixth-order Sauer-Pai synchronous-machine models, IEEE Type-I AVR models where present, ZIP loads, fault-capable pi branches, and TGOV1 governors with an explicit valve slew-rate limiter added to the governor servo state.

The TGOV1 valve position uses the IEEE39 data limits Vmin=0 and Vmax=1 pu. The added valve opening and closing rate limits are both 0.10 pu/s. These are explicit study actuator-envelope settings, not manufacturer-specific settings for an actual generator.

## Disturbance and protection

A three-phase fault is applied to branch 11 (bus 5-8) at 0.10 s. A scheduled line-clearing protection action opens the branch at 0.20 s, giving a 100-ms clearing delay. The event log records both operations.

This is a time-coordinated fault-clearing action. It is not an inverse-time overcurrent relay model, and the experiment does not claim a current-threshold relay characteristic.

## Feeder restoration actuator

Three otherwise identical cases are simulated:

- hold: no post-fault feeder pickup;
- rate_limited: 10% pickup command beginning at 2 s, applied at 0.02 pu/s with a 1.00-1.10 pu amplitude envelope;
- step: the same 10% pickup is applied instantaneously at 2 s. This is an intentionally inadmissible diagnostic control, not a physically acceptable controller.

The sampled feeder actuator is updated every 50 ms in the rate-limited case. Actual applied setpoints are written to feeder_pickup_actuator_trace.csv.

## Recorded evidence

- frequency_trace.csv: all ten generator rotor frequencies, center-of-inertia frequency, frequency deviation, and COI RoCoF;
- governor_actuator_trace.csv: TGOV1 valve position and turbine state for all nine governed machines;
- feeder_pickup_actuator_trace.csv: requested and applied pickup, amplitude envelope, and measured slew rate;
- protection_events.csv: fault and line-trip event timestamps;
- dynamic_summary.json: frequency nadir/peak, maximum deviation/RoCoF, governor and feeder actuator checks, and model scope.

## Interpretation boundary

The IEEE39 test system is synthetic. This experiment supplies electromechanical transient evidence, not EMT switching transients, relay hardware validation, field actuator characterization, or proof of controlled invariance. The scheduled 100-ms line trip and explicit actuator envelopes must be described exactly as modeled. Dynamic voltage, frequency, actuator, and protection evidence must not be merged with quasi-static AC metrics as if they came from one solver.

## References

- PowerDynamics.jl IEEE39 modeling tutorial: https://juliaenergy.github.io/PowerDynamics.jl/stable/generated/ieee39_part1/
- PowerDynamics.jl IEEE39 transient simulation tutorial: https://juliaenergy.github.io/PowerDynamics.jl/stable/generated/ieee39_part3/
- Texas A&M IEEE 39-bus system description: https://electricgrids.engr.tamu.edu/electric-grid-test-cases/ieee-39-bus-system/
- TGOV1 model documentation: https://build.openmodelica.org/Documentation/Dynawo.Electrical.Controls.Machines.Governors.Standard.Steam.TGov1.html

Workflow execution is serialized across the three scenarios so the pinned Julia dependency graph is installed once per run.

The Julia workflow declares the ModelingToolkit and SciML packages used directly by the experiment script.

Only the latest dynamic workflow run is retained as active; superseded dependency-resolution attempts are cancelled to avoid duplicate installations.
