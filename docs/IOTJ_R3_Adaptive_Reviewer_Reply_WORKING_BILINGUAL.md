# IoT-J (IoT-76369-2026) — Adaptive credibility attack response / 自适应信誉攻击审稿回复
> **Evidence status:** Method, code and short-budget smoke verified; full 130-run 1000-episode matrix is executing. This file is a working reply and contains NO invented numerical outcomes. The independent audit generates the final English/Chinese response and results table only after full completion.

## Reviewer comment / 审稿意见
The utility--drift credibility weighting in Eqs. (19)--(21) uses client-reported recovery utility, sparse updates and prototypes; attacks expressly maximizing accepted malicious weight are not demonstrated by fixed random, scaled, sign-flipped or joint forgery. Report independent attacks that jointly manipulate these uploaded quantities across strengths, accepted malicious weights, restored-load and safe-recovery degradation, and compare the recommended IoT physical security, VFL+ and BRPPFL literature according to the appropriate threat model.

## Response in English (protocol-verified, numerical results withheld)
We thank the reviewer for identifying the distinction between ad hoc message forgery and a rule-aware adaptive weight-maximization attack. We agree that fixed joint corruption, although already revealing high accepted malicious weight, does not establish robustness against an attacker explicitly optimizing the credibility formula. We have implemented a deterministic, constrained, rule-aware message search against the **original** utility--drift scorer without altering its clipping, utility cap or prototype comparison.

The compromised clients can jointly choose sparse support and update values, reported utility and representation prototypes. Their search uses their own candidate uploads, the previous publicly broadcast model increment and prototypes, and their own preceding accepted weight and score; it cannot inspect current honest private uploads or optimize against held-out restoration results. We isolate a weight-maximizing objective from a damage-aware objective that seeks to oppose the previous public global update, because exploiting the epsilon denominator can yield high accepted weight even for a nearly zero-valued malicious update. The latter need not imply poor physical recovery.

The frozen evaluation uses a ten-client IEEE39 quasi-static AC restoration setup with two colluding clients, five training seeds (90--94), 1000 training episodes and ten independent held-out evaluations per seed. We fix coalition size and vary manipulation strength over 0.25, 0.50, 1 and 2, retaining clean and fixed joint-fraud controls and metadata/update/prototype component ablations. Each condition is evaluated with the original uncapped scorer and a separately labeled per-client 0.20 weight cap. We report accepted malicious-client fractions, per-round aggregate malicious weight, restored-load and recovery-path AUC, safe-dwell success, paired seed-level degradation and confidence intervals. Because the server clips updates and utility, higher nominal strength can saturate.

**Interpretation and evidence gate.** The original utility--drift scorer is not Byzantine-secure by construction; the 0.20 cap is a new, separately analyzed mitigation, not a retroactive property of the original approach. The experiment is on quasi-static AC power flow and does not establish transient frequency safety or any worst-case convergence theorem. All numerical claims are withheld until the complete 130-condition matrix passes the independent SHA256/checkpoint/training-budget/score-arithmetic audit. The final manuscript table and this response's quantitative statements are then generated from audited real trajectories, not anticipated outcomes.

Regarding related literature, Cao et al.'s 2022 IoT-J NOMA-assisted semi-grant-free secrecy work (DOI 10.1109/JIOT.2022.3193189) and 2021 T-IFS energy-harvesting jammer work (DOI 10.1109/TIFS.2020.3023277) are cited as complementary physical-layer security contexts. Dai et al.'s VFL+ (DOI 10.1109/TETCI.2025.3543769) is differentiated from heterogeneous same-model shared-backbone collaboration. Zhang et al.'s BRPPFL (DOI 10.1016/j.comnet.2026.112498) is compared at the Byzantine learning threat-model level but not misrepresented as a directly executable power-grid recovery baseline.

## 中文回复（已验证实验方案，数值结论待独立审计）
感谢审稿人指出固定联合伪造与以最大化自身聚合权重为目标的自适应攻击之间存在实质区别。我们认同：原稿的随机、缩放、符号翻转及固定规则联合攻击，不能证明原始 utility--drift 权重规则可以抵抗规则感知型自适应投毒。本轮在**不修改原服务器评分、验收和裁剪逻辑**的前提下，新增满足相同上传校验约束的离散规则感知搜索，同时操纵稀疏上传索引及数值、上报恢复效用和原型。

攻击者仅利用自身上传、上一轮公开模型变化和全局原型，以及其自身上一轮已公布的聚合权重和评分；不能读取当轮诚实客户端私有上传或利用留出测试集恢复结果调参。实验区分“最大化被接受权重”和“在被接受权重下增加方向性破坏”两类目标，防止把高权重直接误判为更大的物理恢复损害。

完整协议固定 IEEE39 十客户端、两个协同恶意客户端、五个训练种子（90—94），每组训练 1000 回合、留出评估 10 回合；自适应强度为 0.25、0.50、1、2，保留无攻击、旧版固定联合伪造、元数据消融、更新消融和原型消融，并分开报告原规则与单客户端 0.20 限权变体。每组均报告恢复负荷、恢复曲线均值、安全驻留、恶意客户端验收比例、被接受的恶意合计权重及相对同配置无攻击条件的配对下降。以训练种子为统计单位，不能把轮次和评估回合当作独立种子。

目前仅完成攻击实现、单元测试及短预算 IEEE39 冒烟实验，尚未取得完整正式矩阵的独立审计结论，因此**不填入任何臆测的性能增益或损失数字**。只有当所有 130 组正式运行通过 JSON、检查点 SHA-256、回合数量、评分算式和限权审计后，才把真实数据生成到论文结果表和中英文定稿中。原有信誉规则没有 Byzantine 保证，0.20 限权仅是独立对照；准静态 AC 实验也不能代替频率动态安全证明。

引言已按安全层级引用并区分 NOMA 两篇物理层保密文献、VFL+ 纵向联邦学习与 BRPPFL Byzantine 防护工作；不以不相同的任务或实验平台进行未经验证的准确率数值对比。

## Reproducibility pointers
- R3 branch: https://github.com/startkz/AEFC/tree/experiment/iotj-76369-r3-adaptive-strength-20261110
- Smoke: https://github.com/startkz/AEFC/actions/runs/42743867132
- Full-budget run: https://github.com/startkz/AEFC/actions/runs/42744329117
- Source: `iotj_bridge/adaptive_attack.py`, `strict_run.py`, `audit_adaptive_strength.py`
- Protocol: `docs/IOTJ_R3_Adaptive_Strength_Protocol_20261110.md`
- Conditional paper insertion: `Experimental-RRDRQL.tex`
