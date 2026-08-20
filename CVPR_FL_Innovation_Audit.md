# CVPR Federated/Distributed Learning Audit for AEFC-FRL Revision

This note records how the local CVPR federated/distributed learning papers were used in the TDSC revision. It is not a replacement for formal citation verification, but it captures the mechanism-level evidence extracted from the local PDFs.

## Mechanism-Level Takeaways

| Theme | Local CVPR evidence | Relevance to AEFC-FRL |
|---|---|---|
| Heterogeneous personalization | FedARA separates shared and personalized components and uses anchor-driven representation alignment for heterogeneous edge devices. | Supports the revised shared-backbone plus local-adapter design. |
| Deployment-time shift | Fed-ADE estimates uncertainty and representation dynamics to adapt under client-specific distribution shift. | Supports adding prototype-drift scoring to AEFC credibility. |
| Prototype/domain alignment | FedDAP constructs domain-aware prototypes under domain shift; F2DC decouples and calibrates domain-skewed features. | Supports recovery-state prototypes as a compact latent alignment signal. |
| Privacy boundary | DP-FedAdamW and personalized federated diffusion models provide formal DP framing; FedMOP evaluates gradient leakage. | Supports the paper's conservative privacy wording and gradient-leakage discussion. |
| Communication efficiency | OS-Fed and other compression-oriented FL works show that communication reduction alone can harm convergence if update structure is ignored. | Reinforces AEFC's recovery-aware sparse update selection rather than generic Top-k compression. |

## Revision Decisions

1. AEFC-FRL now aggregates only the shared recovery backbone. Local observation and action adapters remain client-side.
2. Recovery-state prototypes are used to align latent recovery semantics and measure subsystem drift.
3. Server credibility now includes a shift-consistency penalty in addition to advantage and update norm.
4. Related Work cites the CVPR papers as general heterogeneous-FL and privacy-FL evidence, not as CPS security baselines.
5. Experiments include a heterogeneity and shift stress test to evaluate adapter and prototype contributions.

## Integrity Boundary

The CVPR papers are used to motivate mechanism design. Claims about CPS recovery, cross-layer attacks, and safety remain grounded in the present manuscript's CPS experiments and TDSC/CPS literature.
