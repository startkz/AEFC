# TDSC-R1 — IEEE39 原生全状态估计与可达集审计（2026-11-25）

> **状态：P0 已部分实施，但完整 IEEE39 安全认证尚未通过。** 本文档只记录通过真实源码、实际 MathWorks R2024b 工件与 GitHub Actions 核验的证据，不使用推测数据填补空缺。

## 1. 实验溯源与范围

本分支基于 `audit/tdsc-r1-ieee39-native-20261125`，保留上一阶段的独立液压 SIL 结果及旧版 IEEE39 原稿 560 回合实验，原始轨迹未覆盖。新模型独立构建为 `IEEE39BusSystem_AEFCUnpriv`，由官方 MathWorks IEEE39BusSystem R2024b 源模型插入 4 路合法 Pref 增量控制口与物理转速观测。

历史 MATLAB 原生实验的首个工作流失败并非“算法恢复失败”，而是离线攻击源 `AEFCNativeAttackHarness` 在 Simulink 快速重启时 `center`/`scale` 私有状态未初始化。该问题已通过逐阶段错误日志定位，采用惰性初始化、`saveObjectImpl/loadObjectImpl` 和攻击时窗重置后重新验证。新的在线控制器亦增加相应 Fast Restart 状态初始化保护。保留旧失败 CI 作为审计证据。

## 2. 原始 IEEE39 的状态事实

以**未篡改的官方 IEEE39BusSystem 模型**启用 Simulink `SaveState` 记录，得到真实文件：

- Simulink 模型共有 **9102** 个块。
- 完成 `xout` 日志记录的 **201** 个条目，共计 **976** 个数值分量，但**不能将其解释为 976 个独立的物理动态状态**。逐条检查发现：发电机 AVR/励磁器 150 条、150 分量；调速器/原动机 30 条、30 分量；`Grid/Solver Configuration/EVAL_KEY` 求解器内部 21 条、796 分量，其中 `STATE_1` 单项就有 756 分量，另 20 条各为 2 分量输入缓存。保存变量的数据形状既不证明其为独立物理自由度，也不能自动覆盖母线代数电气量。
- 原先已验证的无特权在线控制接口仅有 **4** 路发电机物理转速，及 **4** 路 Pref 控制映射，不能由四维灵敏度矩阵证明这 976 个或更多系统状态的覆盖性。
- 进一步扫描确认原生模型中 **10 台发电机**均有独立可探测的 `Governor/w` 物理转速信号。新 `aefc_ieee39_attach_all_generator_speeds.m` 将其接入**离线物理评价**日志，未将隐藏 Simulink `xout` 当作防御器在线状态。十转速覆盖全部机组转速，但仍不代表网络全状态。

原生状态清单 CI：
<https://github.com/startkz/AEFC/actions/runs/45538337481>

全部机组转速映射与独立复核：
<https://github.com/startkz/AEFC/actions/runs/45538622715>

## 3. 已实现的条件性全状态算法（不等于真实 IEEE39 全状态认证）

### 3.1 合法在线信息链

`AEFCNativeAttackHarness` 持有实验场景、恶意客户端模拟和后屏蔽攻击调度，向在线控制器仅提供可接收的测量、知识报告、上行模型更新、年龄元数据。在线 `AEFCNativeController` 不接触攻击者身份或同种子干净轨迹。基础测量信任假设为与受攻击 HMI 分离的机组本地转速。

### 3.2 集合型全状态观测器

新增 `aefc_native_interval_observer.m`，对**已独立验证**的离散状态空间模型

```
x(t+1) = A*x(t) + B*(u(t) + a(t)) + c + w(t)
y(t+1) = H*x(t+1) + v(t+1)
```

执行保守区间传播 `xhat+ = A*xhat+B*u+c`、`e+ = |A|*e+|B|*abar+wbar`，并通过每个物理测量行 `H_i` 的测量误差带收缩状态盒。区间收缩保持集合包含性质，只在给定动力学、测量和模型误差界**全部真实成立**时有效。

MATLAB 真实 CI 已验证 **1920 次** 12 状态、4 可信传感器的合成动态包含测试，最大 `abs(x_true-xhat)-e` 为负；缺少先验或测量映射验证时拒绝建立证书：

<https://github.com/startkz/AEFC/actions/runs/45538932867>

### 3.3 执行硬约束与采样间可达包络

已将观测器接入 `aefc_native_full_state_contract.m`：对鲁棒一步预测计算

```
mu = A*xhat+B*u+c
sigma = |A|*e+|B|*abar+wbar
state_lower+sigma <= mu <= state_upper-sigma
input_lower+abar <= u <= input_upper-abar
```

新增 `aefc_native_hold_reachability.m`：若各状态分量在控制保持区间内有经证明的导数上界 `|dx_j/dt|<=F_j`，则以 `[xhat-e-dt*F, xhat+e+dt*F]` 检查连续区间安全。只有采样一步与保持区间**同时**可行，且有验证过的应急控制权限，`aefc_native_certified_execution_step.m` 才授权额外控制修正。

**实测合成测试：** 12 维完整状态、4 个合法测量接口的 **800 次**随机执行通过；刻意移除全状态覆盖或保持区间导数证明时全部拒绝。

<https://github.com/startkz/AEFC/actions/runs/45539035020>

目前官方 IEEE39 尚未提供完整的经验证 `A,B,H`、非线性/DAE 外包络、真实传感器认证、状态估计误差或应急备用控制可行性证明。故此条件性合成求解器不可宣称等价于真实 IEEE39 完整 CBF/CLF。MATLAB 浮点区间运算也需要外向舍入误差分析，不能仅凭固定小 `roundoff_inflation` 自动升级为数学严格证明。

### 3.4 原生接入但强制 Fail-closed

`AEFCNativeController.m` 的严格路径现在直接调用 `aefc_native_certified_execution_step`，从载入器 `aefc_native_load_verified_state_contract.m` 获取经过锁定哈希的模型、初始可信状态区间与证明配置。仓库明确不存在可满足全部条件的真实 IEEE39 证书，因此当前严格模式只能拒绝额外 Pref 修正（不代表旧模型自身的 governor 安全已获认证）。四转速实验使用的代理安全检查器仅可用于**诊断模式**。

## 4. 完整 IEEE39 认证仍缺的实际证据

`configs/ieee39_fullstate_certification_requirements.json` 与 `analysis/audit_ieee39_fullstate_gate.py` 以机器可读形式冻结验收条件：

1. 全部相关发电机、调速/励磁器、转子角、母线电压、支路潮流等安全状态的测量或**真实可覆盖的状态集合**；
2. 覆盖真实 MathWorks 39 母线系统全部差分与代数约束的保证性模型误差界及一步可达包络；
3. 采样保持间隔的连续状态覆盖、受攻击执行器输入界及数值舍入误差；
4. 实际已验证的紧急回退动作和求解失败时的可行保护行为，包含原有调速器；
5. 在一致的完整执行权限下，六方法独立配对攻击后**真实失效与恢复**事件，必须提供不利与右删失样本的完整原始日志。

仅采样状态安全、母线电压或机组速度的正常表现不能独立满足全部上述条款。当前证明门槛明确返回 `BLOCKED` 而不是 `PASS`：

<https://github.com/startkz/AEFC/actions/runs/45539356990>

## 5. 六方法同执行合同实验的证据边界

新原生脚本 `aefc_ieee39_unprivileged_joint.m` 采用相同的末端四转速代理监督器，对比 AEFC-Full、Supervisor-only、RobustAgg、AEFC-no-PATBU、AEFC-no-Gate 和 AEFC-no-TGOPA。独立记录 4 个控制器观测转速、10 个真实机组转速、每个采样的发布控制、执行端攻击与风险门，并使用**攻击结束时恢复集合外 + 随后连续 20 点在内**判定真实恢复事件。

任何方法若未在攻击结束时进入恢复集合外，**不计作恢复成功**；若无法持续保持，则记为未恢复/删失。全机组转速判据比旧四通道判据更广，但仍不代表全电网安全。

真实远程实验运行需以最终完成的 CI 工件而非源码预期为准。若条件触发前 R2024b 的执行失败，则不输出虚构成功率。

## 6. 论文写回原则

目前可以陈述：“提出并实装了无特权在线链条与条件性保守集合估计、鲁棒执行及采样保持区间检查；合成模型上通过随机包含与失败拒绝测试，原生 MathWorks 39 母线模型完成动态状态与十台发电机物理测量路径审计。”不能写成“已证明全部 IEEE39 状态连续安全、AEFC 实现可信物理恢复、或六方法已经显示 AEFC 改善”等未经独立验收结论。

下一项确定性工程工作是从原生模型提取对应的可观测安全状态映射，验证真实电网差分/代数可达集与误差界，建立真实备用命令安全合同，再用新的冻结独立种子验证六方法可归因的恢复优势。


## 11. 2026-11-27 addendum — native electrical topology, branch parameters, and measurement instrumentation

### 11.1 Bus16_1 physical exposure is now confirmed on ten preregistered seeds

[Run 45924335524](https://github.com/startkz/AEFC/actions/runs/45924335524) passed the native MATLAB simulation and independent audit for 20 episodes (AEFC-Full and Supervisor-only, seeds 80–89). All 20 episodes were outside the frozen recovery set during the Bus16_1 fault and satisfied the frozen 20-sample recovery predicate after clearing. The first recovery time was 2.0833 s after fault clearing in every episode.

Strict execution released zero added Pref corrections, invoked zero backup actions, and produced pointwise-identical AEFC-Full and Supervisor-only physical trajectories. Cross-seed physical trajectories were also identical because seeds affect offline client-packet generation, not the native plant disturbance. This is a confirmed native post-fault recovery baseline, not an AEFC physical recovery-gain result or ten independent physical samples.

### 11.2 Complete bus-port current topology

[Run 45930674491](https://github.com/startkz/AEFC/actions/runs/45930674491) resolved all 123 busbar-port current series across 41 physical bus sections. The mapping uses the native alternating convention I_(2k-1)=LConn_k and I_(2k)=RConn_k; all 123 ports are mapped. The five composite busbar ports are reconciled through three current-conservation relations. The remaining current families include 68 three-phase line-terminal vectors and 24 transformer winding vectors. These are offline simulator records, not trusted online sensors.

### 11.3 Native branch parameter equivalence to MATPOWER case39

[Run 45932665618](https://github.com/startkz/AEFC/actions/runs/45932665618) verified all 34 line R/X/B values and all 12 transformer winding R/X sums against the fixed MATPOWER case39 reference.

For native three-phase lines, the positive-sequence conversion is R1=R-Rm, L1=L-M, and C1=Cg+3Cl. Maximum relative errors were 0.0070% for R, 0.7814% for X, and 3.3888% for B, within the declared 0.1%, 1%, and 5% tolerances. MATPOWER RATE_A is now usable as a benchmark reference for the 34 345-kV lines after correct RMS-current calculation; it is not a validated conductor thermal limit.

The 12 transformer winding resistance/leakage-reactance sums match the MATPOWER branches with maximum absolute errors of 1e-4 p.u. and zero, respectively. Native transformer blocks declare SRated=100 (unit MW), with three 345/345-kV and nine 345/22-kV configurations. MATPOWER transformer RATE_A is not applied to the native winding thermal limit. Tap equivalence and the native rated-apparent-power interpretation still require review.

### 11.4 Online measurement port audit and sensor candidates

[Run 45932082411](https://github.com/startkz/AEFC/actions/runs/45932082411) confirms 70 PS-Simulink Converter blocks in Generators and zero in Grid. Ten rotor-angle, ten rotor-speed, and ten generator-terminal-voltage signal candidates are present. Busbar, line, and transformer blocks have no signal output ports. AEFCNativeController still receives only four physical speed measurements.

The existing Generators output bus has one top-level output connected to the Measurements subsystem. The latter selects mGenX.w and mGenX.Vt (20 fields) into two ten-input Muxes; each generator Bus Creator has three inputs, leaving one generator signal not selected by the current Scope. A runtime probe [Run 45933102123](https://github.com/startkz/AEFC/actions/runs/45933102123) captured a 30-dimensional generator measurement vector over seven samples. The updated probe is extracting its first/last values and bus object metadata to determine exact channel ordering.

The Simscape Electrical library exposes native three-phase Current Sensor, Line Voltage Sensor, Phase Voltage Sensor, and Current-and-Voltage Sensor blocks. [Run 45932871101](https://github.com/startkz/AEFC/actions/runs/45932871101) confirmed their physical-signal output ports can connect to the native PS-Simulink Converter. This validates library-level compatibility only.

### 11.5 Single-point sensor insertion pilot

[Run 45934020640](https://github.com/startkz/AEFC/actions/runs/45934020640) is running a single-point insertion experiment: a Line Voltage Sensor at Bus16_1 and a series Current Sensor between Bus16_1/RConn1 and B16–B17/LConn1. The wiring removes only that specific physical branch and preserves the shared Bus16_1 fault connection. The audit will compare sensor outputs against native Simscape voltage/current series and compare all 41 bus-voltage and ten-generator-speed trajectories against the no-sensor seed-80 baseline. No full-grid sensor coverage claim is made until this pilot passes.

### 11.6 Full-state promotion gate recheck

[Run 45934329179](https://github.com/startkz/AEFC/actions/runs/45934329179) reran the independent promotion gate after the latest topology and parameter evidence was added. The result remains BLOCKED, with 18 blocking requirements, including incomplete online observer coverage, no full-state measurement map or error-bound proof, unverified physical predicates, no validated sampled/intersample nonlinear DAE reachable tube, uncertified emergency Governor viability, and no independent six-method recovery holdout.

The offline current/topology/parameter evidence improves model understanding and sensor-insertion readiness. It does not satisfy trusted online measurement, continuous-time reachability, or emergency-control certification. The manuscript promotion gate must remain blocked.
