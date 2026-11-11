# IoT-J R4 — Reviewer response work plan: equal-byte coordinate selection, advantage error and heterogeneous adapters

**Evidence state (do not confuse with results):** code and independent smoke for coordinate selection and paired physical advantage are verified. The frozen 10-seed, 40-cell full-budget IEEE39 coordinate experiment and separate 10-seed frozen-checkpoint advantage replay are executing in GitHub Actions. No formal experiment numbers or final reviewer conclusions have been assumed.

This is additional **quasi-static IEEE39 AC** evidence; original six-method Simulink–Python Fig. 5/6 remains a different source. Prior Fig5/6 AC material is preserved on branch \`experiment/iotj-fig56-episode-traces-20261111\`.

## A. Correct mathematics, with explicit assumptions

Local critic estimate and fixed-policy advantage:
\[
\widehat A_i(s,a)=\widehat Q_i(s,a)-\widehat Q_i(s,\pi_i(s)),\quad
A^\pi_i(s,a)=Q^\pi_i(s,a)-Q^\pi_i(s,\pi_i(s)).
\]
If and only if \(\sup_{x\in\{(s,a),(s,\pi_i(s))\}}|\widehat Q_i(x)-Q^\pi_i(x)|\le\varepsilon_Q\),
\[
|\widehat A_i(s,a)-A^\pi_i(s,a)|\le 2\varepsilon_Q.
\]
In particular, \(\widehat A_i>0\) **does not** prove \(A^\pi_i>0\); to guarantee a positive true policy advantage from this inequality one needs \(\widehat A_i>2\varepsilon_Q\) with the actual valid error bound. It is still only a local policy advantage, not a guarantee of monotonic improvement of the federated global objective. Neither a global \(\varepsilon_Q\) nor a monotonic aggregated improvement is proved by the experiments.

The independent frozen-model physical paired-rollout diagnostic uses training seeds 80–89 and **only the already completed** original 1000-episode AEFC checkpoints from Actions run [42940416216](https://github.com/startkz/AEFC/actions/runs/42940416216), source SHA \`0af6e066ff385b191b2db3b86a40adc2ad79956f\`. Its separate held-out demand seeds \`200000+100*seed+profile\` (not training seeds and not terminal evaluation seeds) produce identical AC initial states and operational demand for each pair. From each reachable state, it compares (a) current policy action with (b) a signed local action deviation, keeping every other client on the same frozen policy. Paired discounted finite-horizon returns estimate *current-policy* \(A^\pi_i\) on the **sampled** states, not optimal \(A^\star_i\). Report estimated/pair return, absolute advantage error, false-positive selection, sign disagreement, \(|\widehat A|\le0.01,0.05,0.10\) margins, training-seed CIs. The actor, critic, training reward and evaluation oracle are unchanged. These empirical values must **not** be called uniform sup error bounds.

## B. Three distinct coordinate-selection rules on one final Adam displacement

The currently **separate** transition-level \`random\` learning baseline samples random *transitions*, not model coordinates, and is not the control asked for in this review.

For each individual client-sharing round, fix the same PER minibatch, positive-advantage subset, weights, loss, Adam hyperparameters and two optimizer steps. Let \(\Delta_i^{Adam}\) be the **final** shared-backbone displacement from that identical optimization. For \(d\) shared parameters and \(k=\lceil0.2d\rceil\):

- \`adv\`: upload the \(k\) largest \(|\Delta_i^{Adam}[j]|\) coordinates and their true \(\Delta_i^{Adam}[j]\) values;
- \`coord_random\`: sample exactly \(k\) coordinate indices uniformly without replacement from a **separate deterministic RNG**, and upload the same final \(\Delta_i^{Adam}[j]\) values;
- \`coord_gradtopk\`: sum the absolute raw pre-Adam gradients \(\sum_{u=1}^{2}|g_{i,u}[j]|\), select its top \(k\) coordinates with deterministic ties, but upload \(\Delta_i^{Adam}[j]\) at those coordinates. This does **not** select the final Adam coordinate magnitude.
- \`ordinary\`: existing ordinary-loss Top-\(\kappa\) comparator, retained and explicitly separate from the coordinate-only ablation.

Zero positive-advantage selection produces the same padded zero sparse message for all methods. Real application-layer serialized messages contain identical uint32-sized indices/float32 values, utility field and prototype payload; \`--fixed-traffic\` pads absent prototype categories to equal byte sizes. The independent full auditor must verify **per-client byte sums and per-round equality**, not merely extrapolate bytes from \(k\).

The frozen full experiment has **10 paired seeds (80–89), four methods, 5 heterogeneous clients, 1000 episodes × 30 steps, 200 federation rounds, 10 held-out evaluations**, IEEE39 \`hetero=dim\`, clean, local steps 5, sharing steps 2, batch 256, hidden 128, latent 32, \(kappa=.2\). Independent training seeds are the uncertainty unit; the same seeded demand and held-out evaluation identifier is used across methods. Record real terminal load, process AUC, safe five-step dwell, censored recovery (step \(-1\)), restricted 31-step score, message byte totals and selected support/delta hash. The 31-step score for nonrecovery is **not** measured physical recovery time.

Only a 40/40 fail-closed audit permits publishing the actual method comparison. No variance or advantage ranking is pre-assumed. Separate earlier IoT-J AC 1000-episode queues are **not** pooled into this matching protocol.

## C. Adapter geometry and \(2^3\) physical heterogeneity design

The existing policy is \(g_{\xi_i}(b_\theta(e_{\psi_i}(o_i)))\) with **local observation adapter** \(e_{\psi_i}\), globally aligned backbone \(b_\theta\) and **local output/action adapter** \(g_{\xi_i}\). Local critic remains private.

Model shape frozen for the full experiments:
- observations: odd-indexed clients use 3 features in dimension-limited groups, remaining clients use 6; other groups use 6 per client;
- local encoder: \(d_i\rightarrow128\rightarrow32\); shared backbone \(32\rightarrow128\rightarrow128\rightarrow32\); local head \(32\rightarrow128\rightarrow1\) (bounded sigmoid action);
- local encoder parameter count: 5,024 (\(d_i=6\)) or 4,640 (\(d_i=3\)); shared backbone 24,864; local head 4,353, assuming bias in every linear layer;
- shared latent dimensionality 32, not a proof of semantic agreement;
- local actor adapter and critic train in \`local_fit\` while the backbone is frozen; shared-actor learning subsequently freezes adapter/critic and updates only the backbone; the globally aggregated backbone is then synchronized.

**Factor controls:** observation dimension (6/3); odd client valve/pickup command bound (0.6); honest demand shift (+6% from AC step 12 in odd clients). The implementation now supports all eight binary combinations: \`base\`, \`dim\`, \`saturation\`, \`shift\`, \`dim_saturation\`, \`dim_shift\`, \`saturation_shift\`, \`dim_saturation_shift\`. Original standalone scenarios remain unchanged.

Four learning configurations should be named precisely:
- AEFC-FRL: standard \`adv\`;
- adapter-training frozen: \`adv --disable-adapters\` — the adapter **architecture remains present**; this is not "no-adapter" model removal;
- prototype alignment disabled: \`adv --disable-proto\` — server metadata prototypes may still exist; this does not remove all prototype usage;
- dense FedRL: \`dense\` — the sparse budget does not apply to FedRL; log actual bytes and do not claim equal traffic.

A physical-semantic diagnostic must evaluate actual unsafe/recovering/stable operational labels, class support, cross-client assignment and physical restoration; raw prototype distance or the same latent dimension alone does not show semantic compatibility. Interaction outcomes require a factorial model or paired contrasts at the **seed** level and explicit non-Gaussian/ceiling limitations. A smoke check over 8×4 cells is only structural, not an empirical recovery comparison.

## D. Publication gate and bilingual reviewer response

The numerical manuscript section, supplementary appendix and English/Chinese rebuttal MUST be written only after the required full workloads and independent audits complete. Paper theory will retain the conditional \(2\varepsilon_Q\) inequality, distinguish empirical errors from uniform bounds, and not claim all accepted advantages yield global gains. Fig. 5/6 from the original Simulink paper are not silently replaced.

Evidence sources:
- coordinate smoke: https://github.com/startkz/AEFC/actions/runs/42956431621
- coordinate full: https://github.com/startkz/AEFC/actions/runs/42957084297
- diagnostic smoke: https://github.com/startkz/AEFC/actions/runs/42957909938
- diagnostic full: https://github.com/startkz/AEFC/actions/runs/42958431836
- factorial interface smoke: https://github.com/startkz/AEFC/actions/runs/42958645635

All final numerical statements must link exact code SHA, GitHub Actions run and archived raw inputs, report failures/censoring, avoid pseudo-replication, and preserve negative outcomes.


## E. Completed full-budget evidence snapshot (2026-11-11)

The three full-budget evidence gates are now complete and independently rechecked:

- Coordinate selection Run 42957084297: 40/40 JSON/PT/manifest triplets; 40,000 training episodes, 8,000 rounds, 400 held-out tests; per-round application-byte equality across all four methods within each seed. Source SHA e674db8b7d00ce908614154bd6f3f21c1a3495ce; result commit c5a81519061ea08d445d6c59b79d631b91468027; detached-manifest result commit 4db9bfa66e04c64013ca48aab27eccd988f9ad77.
- Heterogeneity Run 42959386414: 96/96 JSON/PT/manifest triplets; 96,000 training episodes, 19,200 rounds, 960 held-out tests; all three physical interventions checked from traces. This is a three-seed exploratory pilot only. Source SHA be2d40a4c884a9b6730607e9bbfd8a045e9190db; result commit 51ba84c7a5d4bf80615fe4b39de7087973adca8e; detached-manifest result commit f22392f84f880732fcb8aa125b5f7a5111e5acd3.
- Applied aggregate Run 42962801194: 10/10 seeds, 10,000 training episodes, 2,000 rounds, 100 held-out tests and 90 paired physical profiles; 4,206 training episodes right-censored. The actual updates were nonzero, but the measured pre/post effects did not support stable positive improvement. Source SHA 65f28231f3c3d13d8a50893cc99f224edf670faa; result commit 3f6c98a0f290caa92f49e4d60df8a456efd205bf; detached-manifest result commit d812219af934d8841543b24e9afba73ea0aa57a8.

The independent manifest inventories contain 40, 96, and 10 detached manifest SHA256 values respectively. The raw archive digests are recorded in the bilingual working responses and the standalone integration delta. The 10-seed advantage-error replay Run 42958431836 remains limited to 396 sampled finite-horizon current-policy comparisons; it does not prove a uniform epsilon_Q bound.

No native six-method Simulink–Python Fig. 5/6 reproduction has been performed by the quasi-static AC platform. The repository's current LaTeX entry point still compiles the separate PATBU/Risk-Gate TDSC manuscript; no LaTeX file was modified. The standalone integration delta is docs/IOTJ_R4_AEFC_FRL_Integration_Delta_20261111.md.
