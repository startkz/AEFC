# Independent low-stress confirmation protocol (frozen before confirmation)

**Experiment:** TDSC-R1 hydraulic SIL sampled execution-contract and physical recovery chain.

The first 10-seed strong-stress evaluation at seed 240–249 showed no recovery exposure and an explicit execution-contract refusal in all 20 physical/joint episodes (steps 130–131). It must remain a negative feasibility result and must not be replaced.

An exploratory attack-feasibility scan used seeds **200–204**, three predeclared levels (post-shield attack / bounded load disturbance): `0.015/0.002`, `0.025/0.0035`, `0.040/0.005`. It produced, respectively, physical/joint jointly: 10/10 exposed-and-corrected with no contract failures, 4/10 exposed-and-corrected with 6 contract failures, and 0/10 exposed with 10 contract failures. These are pilot findings, not final publication claims. The independent 20-seed middle-tier confirmation (seeds 300–319) is a separate preregistered run.

**Chosen feasibility confirmation tier:** `post_attack_strength=0.015`, `load_stress=0.002` (selected *after* the five-seed pilot but *before* any independent low-tier holdout). Independent seeds **400–419** are fixed and disjoint from all prior pilot/main/early stress runs. No adjustment to `Config` safe-set limits, the recovery tolerances (flow ±0.012, speed ±0.008), 20 consecutive required recovery samples, timing (steps 120–239 attacked) or full robust execution bound (±0.08) is permitted. Any failed event remains right-censored.

The effect of low-tier selection is explicitly disclosed; the holdout does not establish a global guarantee, mean superiority over baselines, deep-FRL efficacy, or IEEE39 native execution safety. The native and hydraulic original controller source remains unchanged.

**Source ref before holdout:** `3407b783107bae85d5d72536ed572382ac9f5e75` plus this protocol; the confirmation workflow must checkout the branch at its triggering commit, run tests, produce full JSONL, then independently recompute every transition and certified margin. A workflow SUCCESS denotes computation/audit completion, not hypothesis success. Report both positive and negative outcomes, including the number of uncovered or refused commands and the proportion of seeds **actually outside the recovery set at attack stop**.

**Important attribution limitation:** a recovery event can be caused by a trusted fallback and robust certified execution, even if the poisoned/learned proposal was rejected. The next experiment must compare identical supervisor with/without the learned proposals, PATBU, TGOPA and Byzantine robust aggregation to attribute efficacy.
