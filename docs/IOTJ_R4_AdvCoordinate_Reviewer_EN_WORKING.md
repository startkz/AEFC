# IoT-J R4 — Reviewer response (evidence-complete working draft)

**Status: numerical evidence complete; not the final manuscript-integrated reply.** The coordinate-selection matrix (40/40), heterogeneous-factor pilot (96/96), formal applied-aggregate study (10/10), and paired advantage-error diagnostic (10/10) have passed their independent audits. The repository's current main.tex is still a different PATBU/Risk-Gate TDSC manuscript, so no LaTeX source has been overwritten.

We thank the reviewer for distinguishing positive estimated recovery advantage from true current-policy advantage and global recovery improvement, and for requesting coordinate-only controls and evidence under heterogeneous observations, actuators, and operating demand. We have added the requested experiments and retained their distinct evidential scope.

## 1. Conditional advantage statement and empirical error

For a fixed policy π, define Aπ(s,a)=Qπ(s,a)−Qπ(s,π(s)) and Â(s,a)=Q̂(s,a)−Q̂(s,π(s)). If both Q estimates satisfy a genuine uniform error bound |Q̂−Qπ|≤εQ at the two comparison points, then |Â−Aπ|≤2εQ. The inequality is conditional on that bound; empirical finite-horizon replay errors do not establish a global εQ bound. In particular, Â>0 alone is not a sign certificate, and no global monotonicity of sparse federated aggregation is claimed.

The frozen-checkpoint physical replay (Run 42958431836; source SHA e18cc5735c85ed9c1a4bcfad82dfe2391320dd2d; result commit 9ec371474e9779bcad3da89f9a252c94e61ed3f9) passed for 10 seeds and 396 paired samples. Mean absolute estimated-versus-finite-horizon current-policy advantage error was 0.05828 (seed-bootstrap 95% CI [0.05102, 0.06672]); the wrong-positive fraction was 9.78% ([6.30%, 13.50%]); sign mismatch was 26.66% ([19.72%, 33.59%]); and 46.89% ([42.49%, 52.50%]) of estimates satisfied |Â|≤0.01. These are sampled-state diagnostics, not uniform critic-error bounds or optimal-advantage guarantees.

## 2. Equal-byte coordinate selection

For each local sharing step, adv, coord_random, and coord_gradtopk use the same positive-advantage objective, selected minibatch, normalized weights, and two Adam steps. The complete final Adam displacement is computed before support selection. adv selects its largest-magnitude coordinates; coord_random samples k coordinates uniformly without replacement; coord_gradtopk ranks the accumulated absolute raw pre-Adam gradients but uploads the corresponding values from the final Adam displacement. The ordinary-loss Top-k comparator remains a separate objective, not a coordinate-only ablation.

Run 42957084297 completed 40/40 cells (seeds 80–89 × four methods), with 40,000 training episodes, 8,000 federated rounds, and 400 held-out tests. The independent audit and detached manifest inventory both passed. Actual application-layer uplink was 40,230,000 bytes per run and matched across all four methods at every round within each seed.

| Method | Mean terminal restored load | Training safe-dwell fraction | Held-out terminal load | Held-out safe-dwell fraction |
|---|---:|---:|---:|---:|
| adv | 95.3615% | 57.85% | 96.2396% | 62.00% |
| ordinary | 94.9362% | 56.87% | 95.2562% | 60.00% |
| coord_random | 94.2450% | 48.99% | 94.9433% | 60.00% |
| coord_gradtopk | 95.3549% | 58.24% | 96.4788% | 63.00% |

Across 10 paired training seeds, adv−coord_random was +1.1165 percentage points (95% CI [0.2989, 2.0374]); adv−coord_gradtopk was +0.0066 points ([-0.0561, 0.0660]); and adv−ordinary was +0.4253 points ([-0.0899, 1.1051]). The held-out terminal-load difference adv−coord_gradtopk was −0.2393 points ([-0.5503, −0.0280]). Thus random coordinate selection was weaker in this setup, whereas raw-gradient Top-k and final-displacement Top-k had similar training results; adv did not dominate every held-out metric. There were 17,805 right-censored training episodes out of 40,000. The restricted score 31 is not an observed recovery time.

## 3. Heterogeneous observation, actuator, and demand factors

Run 42959386414 completed all 96 cells: eight factor combinations × four configurations × three seeds (80–82). Every cell used 1,000 episodes, 200 rounds, and 10 held-out tests, yielding 96,000 training episodes, 19,200 rounds, and 960 tests. The separate manifest audit verified all 96 JSON/PT/manifest triplets and detached manifest SHA256 values. This remains a **three-seed exploratory factorial study**, not ten-seed confirmation.

The observation factor changed client input dimensions from [6,6,6,6,6] to [6,3,6,3,6], with encoder parameter counts checked. The actuator factor capped odd-indexed clients at 0.6; across 2.88 million constrained training increments, 694,093 reached the 0.0108 served-load increment cap, with no cap violation. The demand factor increased odd-client physical demand by 6% at AC step 12; the intervention was verified in 48,000 training episodes and 480 held-out traces.

Selected held-out outcomes illustrate sensitivity to observation heterogeneity. Under dim_shift, adv achieved 90.72% terminal load and 0.167 safe-dwell fraction; dense FedRL achieved 90.57% and 0.133. Adapter-training frozen achieved 99.28% and 1.000, while prototype-alignment disabled achieved 94.36% and 0.900. Under dim alone, adv achieved 93.08% and 0.400, while dense achieved 92.74% and 0.333. Each cell has only three independent seeds; these values and the seed-bootstrap intervals are exploratory and do not establish a population-level ranking. Adapter-training frozen retains the adapter architecture; prototype-alignment disabled does not remove all server prototype metadata. Dense FedRL sends more bytes (199,358,000 per run) than sparse configurations (40,230,000 per run).

Of 96,000 training episodes, 31,613 were right-censored. Failure score 31 is only a restricted comparison code, not a measured physical recovery time.

## 4. Actual applied aggregate-update effect

The formal 10-seed experiment Run 42962801194 is complete (source SHA 65f28231f3c3d13d8a50893cc99f224edf670faa; result commit 3f6c98a0f290caa92f49e4d60df8a456efd205bf). It includes 10,000 training episodes, 2,000 rounds, 100 held-out tests, and 90 paired physical profiles at rounds 50, 100, and 200. All 90 applied backbone updates were nonzero; local adapters, heads, and critics were frozen for the pre/post comparison. The manifest supplement independently verified all ten JSON/PT/manifest triplets.

| Checkpoint | Terminal-load change (pp) | 95% CI | Load-AUC change (pp) | 95% CI | Safe-dwell change |
|---|---:|---:|---:|---:|---:|
| 50 rounds | −0.0115 | [−0.0477, 0.0177] | −0.0316 | [−0.0905, 0.0158] | 0 |
| 100 rounds | −0.0079 | [−0.0254, 0.0072] | −0.0451 | [−0.0993, 0.0051] | 0 |
| 200 rounds | −0.0029 | [−0.1549, 0.1401] | −0.0167 | [−0.0734, 0.0268] | −0.0333 [−0.1000, 0] |

The formal result does not show statistically supported, stable positive recovery improvement from the applied aggregate update. We therefore do not claim monotone global improvement.

## 5. Scope and reproducibility

All new physical evidence is limited to IEEE39 quasi-static AC. The original six-method Simulink–Python Fig. 5/6 has not been reproduced by this AC platform. Recovery is the first five consecutive converged AC steps with at least 90% restored load and no voltage or thermal violation; episodes not reaching this condition within 30 steps are right-censored (recovery_step = −1). Dynamic frequency safety, optimal Q quality, and global aggregation monotonicity remain unproven.

Primary artifacts:
- Coordinate Run 42957084297, source SHA e674db8b7d00ce908614154bd6f3f21c1a3495ce, result commit c5a81519061ea08d445d6c59b79d631b91468027; full Artifact 13830018801, SHA256 4421bb8a925f27f04d14fa48ac8922ff89f6bf9da6583551ce76b975db89879f; manifest supplement Run 42991080229, result commit 4db9bfa66e04c64013ca48aab27eccd988f9ad77.
- Heterogeneity Run 42959386414, source SHA be2d40a4c884a9b6730607e9bbfd8a045e9190db, result commit 51ba84c7a5d4bf80615fe4b39de7087973adca8e; full Artifact 13835176012, SHA256 82a572cb4b44edf8f9ea5f2262921876b625bc47a3e0a203a7a0b716c152144c; manifest supplement Run 42990167631, result commit f22392f84f880732fcb8aa125b5f7a5111e5acd3.
- Applied aggregate Run 42962801194, source SHA 65f28231f3c3d13d8a50893cc99f224edf670faa, result commit 3f6c98a0f290caa92f49e4d60df8a456efd205bf; full Artifact 13831945798, SHA256 759532d8f5af32122b533d5865aac7d97c86515efe98c41434db61033fb45213; manifest supplement Run 42991863092, result commit d812219af934d8841543b24e9afba73ea0aa57a8.
- Advantage-error Run 42958431836, source SHA e18cc5735c85ed9c1a4bcfad82dfe2391320dd2d, result commit 9ec371474e9779bcad3da89f9a252c94e61ed3f9; 396 paired samples.

**Integration limitation:** the current branch's main.tex still compiles the Bounded-Authority/PATBU/Risk-Gate manuscript, not the target IoT-J AEFC-FRL paper. No existing LaTeX file has been modified. This response and the separate integration delta must be merged only into the correct AEFC-FRL manuscript after its source is identified.
