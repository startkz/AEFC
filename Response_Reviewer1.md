# Response to Reviewer 1

We thank the reviewer for the careful and technically important comments. Rather than only weakening several claims, we have reconstructed the manuscript around a stricter trust model. The revised paper is titled **“Trustworthy Heterogeneous Federated Reinforcement Learning for Certified Resilient Recovery of Cyber-Physical Systems.”** Its central problem is recovery integrity when both physical observations and the federated knowledge used for recovery may be untrusted.

## Comment 1 — Typographical error in “Physical”
We agree that the repeated misspelling was unacceptable. The title, running header, source files, and compiled manuscript have been rechecked. The revised title above is now used consistently.

## Comment 2 — Unsupported O(T^{-1/2}) convergence claim
We agree that the previous analysis borrowed too directly from standard SGD and treated compression and credibility errors as assumptions. The revised manuscript removes the unconditional O(T^{-1/2}) claim and reconstructs the theory around mechanism-derived quantities.

First, deterministic Top-k is no longer assigned an unspecified contraction coefficient. We prove

||v-C_k(v)||_2^2 <= (1-k/d)||v||_2^2,

so the contraction parameter is explicitly delta_k=k/d. Second, the previous bounded-credibility-bias assumption has been removed. The server now uses Byzantine-resilient coordinate-wise f-trimmed aggregation under an explicit budget f<N/2. We prove an aggregation-envelope lemma that bounds the server update by the honest coordinate envelope. Third, the remaining learning result is explicitly a conditional non-convex stationarity bound containing stochastic noise, honest-client heterogeneity, Top-k residual, and Byzantine aggregation residual. We do not claim global optimality or unconditional convergence of the full non-stationary MARL process.

Most importantly, the revised paper separates optimization convergence from physical safety. A separate safety theorem guarantees forward invariance of the modeled safe set for arbitrary learned policy proposals under uncertainty-set coverage and shield feasibility. Therefore physical safety does not rely on the FRL optimizer converging.

## Comment 3 — Incorrect use of vertical federated learning and unsupported averaging across heterogeneous spaces
We agree. All “vertical FL” terminology has been removed. The revised setting is **trustworthy heterogeneous federated reinforcement learning**. Each subsystem has a private observation adapter, a shared recovery backbone, and a private action/safety adapter. Only the representation-compatible shared backbone is federated. This avoids direct averaging of incompatible input/output layers.

Recovery-state prototypes are retained only as an alignment mechanism for reducing honest-client representation drift. They are not used to authenticate clients, because a Byzantine participant can fabricate its prototype. The server’s security decision therefore does not depend on self-reported prototype similarity, confidence, or advantage.

## Comment 4 — Power-grid-only validation and simulation-to-real gap
We agree that the strongest empirical evidence remains the IEEE 39-bus and IEEE 118-bus power-grid CPS studies. The revised paper no longer treats those experiments as evidence of broad cross-domain generalization. Existing numerical results are retained only for the claims they directly support: recovery performance, communication cost, scalability, heterogeneity stress, and empirical robustness under the attacks actually implemented.

We also added an explicit security-validation protocol for the newly introduced trustworthy-recovery guarantees. It specifies barrier-margin logging, unsafe-policy injection, adaptive/colluding Byzantine attacks, aggregation-deviation auditing, and code-to-claim traceability. We deliberately do not fabricate numerical certificate results that are not yet produced by the released implementation. The deployment discussion also states the assumptions that must be validated in a physical implementation, including state-estimation uncertainty coverage, shield feasibility, communication delay, stale updates, and certified fallback control.

## Comment 5 — Membership-inference AUC is not a formal privacy guarantee
We agree. The base framework no longer makes a formal privacy claim. Membership-inference AUC is described only as an empirical attack metric. Sparse communication is used for efficiency, not as a privacy mechanism.

For deployments that require quantifiable privacy, the revised method includes an optional trajectory-level differential-privacy extension: per-trajectory contributions are clipped, Gaussian noise is added before data-dependent Top-k post-processing, and the resulting composition can be accounted for with a standard Rényi-DP accountant. A future numerical privacy study must report the privacy unit, clipping norm, sampling rate, number of compositions, accountant, and final (epsilon,delta) budget. These quantities are not claimed for the base method unless the DP extension is actually enabled.

## Additional reconstruction motivated by the review
During the revision we identified a deeper security weakness in the previous credibility-weighted AEFC design: advantage, update norm, and prototype drift were all client-originated quantities and could therefore be spoofed by a Byzantine participant. The revised server no longer treats these values as a trust root. We also introduce a policy-independent robust safety-recovery shield so that failure of the learning layer does not directly imply failure of the physical safety layer.

The revised contribution is therefore no longer a combination of heterogeneous FRL, Top-k compression, and heuristic credibility weighting. It is a layered trustworthy-recovery design with explicit trust boundaries: certificate-gated honest-client knowledge generation, Byzantine-resilient shared-backbone coordination, and certified physical execution.
