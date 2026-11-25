# Native IEEE39 R2024b CI chronology and provenance (2026-11-25)

This is a development log, not an acceptance claim for full-state safety.

| Run ID | Commit/source | Evidence at time of audit |
|---|---|---|
| 45535758103 | 82bc153 | Workflow YAML could not be parsed; no tests executed |
| 45535788651 | 7f355fd | Static audit assertion used incorrect model symbol; no MATLAB run |
| 45535845181 | 247eaa5 | Online no-oracle static audit passed; new real native `IEEE39BusSystem_AEFCUnpriv` build passed; experiment failed because `Simulink.SimulationInput.setBlockParameter` was incorrectly given multiple name/value pairs |
| 45536457263 | 405101c | Synthetic 2-state robust-affine full-state interval test passed in MATLAB R2024b, including 500 samples and fail-closed branches. No native system safety conclusion |
| 45536779234 | 1aa5a77 | Corrected native smoke and strict-mode evaluation, uses single-parameter SimulationInput overrides; inspect the workflow for final status |
| 45536833604 | d823605 | Corrected six-treatment 4-scenario pilot with same four-speed surrogate supervisor; inspect the workflow for final status |

Historical native matrices and original hydraulic SIL datasets are unchanged. The original `AEFCNativeController` oracle-informed implementation is preserved as `AEFCNativeControllerLegacy` on this experimental branch to permit frozen legacy model reconstruction while the active `AEFCNativeController` has no oracle arguments.

## Scientific interpretation

- A successful model build is not an executed simulation.
- A successful executed simulation is not evidence of attack-induced recovery: an attack-end-outside-set observation followed by 20 in-set samples must be measured independently.
- Measured four-generator speed bounds are neither all generator states nor full 39-bus physical safety.
- The native finite-difference sensitivity matrix and assumed proxy residual bound are not validated full-state/hold-interval reachable tubes.
- The full-state affine solver is enabled only when its independently trusted state coverage and dynamic bounds are provided and verified; the original native model does **not** currently provide them.
- Simulator-output-only offline state logs must never be fed back to online controllers as trusted state.
- The successful hydraulic SIL 40/40 recovery from the prior stage was also attained by fixed Supervisor-only and cannot be used as causal proof that FL improved recovery.

### Next independent verification requirements

1. Reconstruct genuine native online state estimation error sets and measured post-attack physical response; reject false recovery events.
2. Add whole-network nonlinear/discrete reachable tube and independently certified emergency backup, then enable full-state contract with separate continuous-time hold-interval assessment.
3. Only after actual native vulnerable/recoverable exposure exists, perform frozen independent paired seeds for AEFC-Full, Supervisor-only, RobustAgg and ablations with the identical safety supervisor and communication/action authority.
4. Keep every failed CI run and unfavorable experimental episode in the evidence archive. Do not tune the recovery threshold to manufacture a success count.
