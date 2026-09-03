# Bounded-authority AEFC implementation status

This branch now contains executable implementations of the mechanisms introduced by the revised TDSC manuscript:

- `aefc/security.py`: PATBU, risk-aware recovery gate, trust-gated adaptation, robust post-shield safety projection.
- `aefc/attacks.py`: observation corruption, recovery-knowledge poisoning, and additive post-shield control-channel corruption.
- `aefc/federation.py`: common-support sparse coordination and coordinate-wise trimmed mean.
- `experiments/run_joint.py`: four-cell physical×knowledge corruption experiment, seven methods/ablations, 20 matched seeds, per-step JSONL traces.
- `analysis/make_results.py`: summary aggregation, figure generation, and automatic LaTeX Results generation from actual trace summaries.
- `experiments/matlab/aefc_ieee39_interface_discovery.m`: native R2024b IEEE39 interface discovery without guessing actuator mappings.
- `.github/workflows/aefc-joint-20seed.yml`: runs the 20-seed mechanism experiment and attempts native IEEE39 bootstrap/interface discovery.

## Evidence boundary

The Python reduced-order backend is an executable **mechanism-integration test**, not an IEEE39 replacement. Its automatically generated Results are explicitly labeled mechanism-level.

Native IEEE39 execution remains conditional on a working MATLAB R2024b license. The previous hosted runner installed MATLAB successfully but failed at runtime license checkout. The new workflow passes `secrets.MATLAB_BATCH_TOKEN` as `MLM_LICENSE_TOKEN`; if that secret is absent or invalid, native IEEE39 results remain unavailable and the paper must not report them.

## Reproducibility chain

`Results-Auto.tex <- results/generated <- results/joint20/summary.csv <- raw JSONL artifact <- experiments/run_joint.py + configs/joint20.json + commit SHA`

The raw per-step traces are uploaded as a GitHub Actions artifact rather than committed directly, to avoid bloating the repository. Summary CSV/manifest and generated manuscript artifacts are committed by CI with `[skip ci]`.
