# P0 Native IEEE39: Real Deployed-Parameter Post-Poisoning Recovery Protocol

**Frozen before results.** Main 560-run, E1/E2/E5 supplemental native 720-run, E5 activation 120-run, and earlier reduced-order P0 studies are read-only. The newly instrumented MATLAB System Object is an independent copy.

## Object under test

The **actual deployed four-dimensional parameter vector** `theta` maintained by `AEFCSupplementalNativeController`, updated by its existing generated seven-client reports, common-support trimmed aggregation, trust-weighted clipping, policy step, and deployment acceptance. This is not an end-to-end trained neural network backbone, nor a certified fixed-point training objective.

An additional diagnostic copy reconstructs synthetic uncompromised reports and runs the same model-specific online update operator on the **same actual observed plant trajectory**. It produces `theta_shadow`. Both full vectors are exported at *every sample*. The shadow cannot affect proposal selection, Gate, shield, downstream attack, or the Simulink plant. This is a matched-input, **dynamic clean-shadow comparison**: not an independently simulated clean plant and not a fixed authenticated convergent target.

**Known limitation**: the original native source code uses oracle knowledge of synthetic report provenance in its online PATBU and references the clean observation when generating client reports. This experiment does not remove those privileges and cannot close the independent P0 for truly unprivileged online input.

## Frozen experimental matrix

- Backend: official R2024b `IEEE39BusSystem`, validated four generator-speed/`Pref` causal pairs, unchanged four-channel normalizations and plant wiring.
- Methods: `FedRL` (1), `AEFC-no-TGOPA` (5), `AEFC-Full` (7).
- Scenarios: knowledge-only (code 2) and joint (code 4); **20 seeds per cell**, 120 native episodes.
- Attack window: steps 15..43 inclusive. Sample period 1/60 s.
- Extended horizon: steps 0..219, **220** samples per episode, **176** samples after the last poisoned step. Plant and controller settings identical to existing Main on the original first 73 samples.
- 7 synthetic clients, 2 poisoned reports, common support 3; all documented PATBU, Gate and adaptation parameters unchanged.
- Full pre-attack shadow identity is required to numerical tolerance 1e-9.
- First-73 native metrics will be compared against authoritative Main, with rejection threshold 1e-8.

## Predefined endpoints

Each episode records `theta_t` and `theta_t^clean-shadow`, per-step Euclidean difference, actual and shadow model acceptance, Gate decisions, trust, individual parameter changes, physical observation and execution signals.

Primary P0 endpoint: **genuine correction** is defined only if the post-stop initial parameter error exceeds **epsilon = 0.001**, and it later enters this tolerance and stays inside for **20 consecutive recorded samples**. Runs initially inside epsilon count as *already within tolerance*, **not recovered**. Never-attained runs are right-censored; do not discard them. Summary reports seed counts, stop-time/final errors and acceptance/rejection intervals. Error increases must be counted, not hidden by mean curves.

Mean stepwise error shrinkage and an empirical maximum adjacent ratio above epsilon may be reported as descriptions, **not** a uniform contractivity constant. Parameter-to-dynamic-shadow distance is not the G3 theorem's distance to a fixed certified target. Attack-stop progress, long-run contraction and accepted-interval assumptions must be separately examined.

Dangerous-proposal zero denominator must remain NE. No claim of continuous-time G5 robustness follows from observed finite samples.

## Workflow provenance

Native run [39538932151](https://github.com/startkz/AEFC/actions/runs/39538932151). Source includes `AEFCNativePostPoisonController.m`, `aefc_ieee39_native_postpoison.m`. Independent audit requires all 120 full trajectories, raw hashes, matched baseline comparison, and exports summary/seed tables. Results cannot be promoted into manuscript tables until audit has passed.
