# Reference Innovation Audit for AEFC-FRL Revision

This note summarizes the useful innovation signals extracted from the local `参考文献` PDF folder and the additional secure-FL literature added during revision. It is an internal author-side audit, not a manuscript section.

## Security and CPS Resilience

- `Foundations of Cyber Resilience` and `Exploring the Quantitative Resilience Analysis of Cyber-Physical Systems` support the security narrative that CPS resilience is about preparing for, withstanding, recovering from, and adapting after attacks. The manuscript should frame AEFC-FRL as post-attack resilient recovery under cross-layer attacks, not only as efficient model exchange.
- `用于增强CPS弹性和数据隐私的分布式智能框架` supports the idea that distributed intelligence in CPS should jointly discuss resilience, data locality, and privacy limits. This informed the stronger introduction-level privacy boundary.
- Improvement adopted: Abstract and Introduction now foreground cross-layer attacks and post-attack recovery as the primary TDSC security problem.

## Federated Reinforcement Learning

- `CyberForce` is the closest TDSC FRL-security comparator. It combines FRL with moving-target defense for malware mitigation and evaluates poisoning resilience. It supports adding a security-oriented FRL paragraph rather than treating FRL as only a distributed optimization tool.
- `FRAMU` and `PreM-FedIoV` show FRL applications in machine unlearning and predictive maintenance. They are useful baselines but do not directly address cross-layer CPS recovery.
- `GenFedRL` provides a general FRL formulation for DRL agents. Its main lesson is that generic model-sharing is not enough for CPS recovery because it does not attach update importance to recovery semantics.
- `A2FC` is important for innovation boundary control. It already uses advantage actor/federated critic ideas in MARL. AEFC should therefore avoid implying that advantage or federated critic concepts are new in isolation. The defensible novelty is recovery-aware sparse update selection plus credibility-aware aggregation under CPS attacks.
- Improvement adopted: Related Work and Methodology now state that Top-kappa sparsification and credibility weighting have precedents, while AEFC's contribution is the recovery-semantic coupling.

## Secure Federated Learning and TDSC Coverage

- ESFL, Byzantine-robust FL, and malicious-client detection papers from recent TDSC volumes show that TDSC reviewers expect FL security papers to name concrete adversaries such as backdoor, poisoning, malicious clients, and Byzantine updates.
- SXGB and OLIVE show the secure-execution/TEE direction. They are useful for clarifying that AEFC is not a TEE, SMC, or formal DP mechanism.
- Runtime backdoor detection for DRL strengthens the point that RL policies themselves are attack surfaces.
- Improvement adopted: Related Work now includes ESFL, Byzantine/privacy-preserving FL, FedDMC, SXGB, OLIVE, CyberForce, and runtime DRL backdoor detection.

## Communication-Efficient FL

- Communication-efficient FL and over-the-air FL references support the communication part of AEFC, but they should not dominate the story. For TDSC, communication reduction is best presented as an enabler of secure recovery under constrained CPS links.
- Improvement adopted: communication is now framed as a constraint during attack-time recovery rather than as the paper's main contribution.

## Items Not Adopted into Main Text

- UAV task offloading, MEC task scheduling, USV incentives, and swarm navigation papers are useful method-adjacent references but less central to a TDSC CPS security paper. Adding too many of them would dilute the security narrative.
- A non-grid CPS experiment remains desirable, but no local executable data are available in the source package. The manuscript therefore discusses PLC/traffic validation as external validity and future work rather than claiming completed cross-domain validation.
