# AEFC v3 独立确认冻结清单（2026-10-22）
**一旦本协议下首个 holdout Actions 开始执行，即冻结全部四项：实验代码、超参数、评价判据和干净影子更新算子。不得使用种子80–119进行调参、删样本、挑选较好的比较器或更换参考定义。**

## 冻结基线（来自成功的探索运行39701661847）
- 来源 Git commit: `b2bf6a079f05d1f0642f9300fcab027869b6a6e9`，探索种子56–63。
- **受保护原控制器** `experiments/matlab/AEFCNativeOnlineRecoveryController.m`：Git blob SHA-1 `4ba08ab5722b8eeb9cf30925a4bdffceb960d3e9`，禁止改写。
- **原生参数** `configs/ieee39_joint20.json`：Git blob SHA-1 `7342b5274d6d357f4c30be0c22025abc34355adc`，禁止改写。
- **已验证的物理映射** `results/ieee39_r2024b/interface_mapping.json`：blob `f2ebdb262c872a76894f8c7408916346756186f4`（bootstrap需重新验证其选择策略，生成文件不作为超参修改）。
- 用于区分本研究与过往版本的原v3在线探索脚本：blob `c8d802f9e19c196cfe852b02a2e8f81f6c776391`。
- 新增脚本 `experiments/matlab/aefc_ieee39_frozen_confirm.m` 仅改变**运行种子及归档目录**，不改变 `AEFCNativeOnlineRecoveryController` 及其模型参数/控制接口。
- 强制 `getOutputSizeImpl` 仍为 `[40 1]` 原生诊断，四维真实 deployed theta。
- 4方法：`AEFC-Unprivileged`、`AEFC-Checkpoint`、`AEFC-OnlineRelearn`、`AEFC-ContractiveReentry`；3场景：clean, knowledge, joint；每方法每场景种子80–119、各40回合；共 **480回合×480点=230,400采样点**，12个10种子分片只为减少运行时间和单独校验哈希。
- 原攻击步15–43，攻击后索引从44开始；与成功探索版完全相同的检测scatter 0.35、clean-streak 3、prox `lambda=0.08`、跟踪L2≤0.01、观测/物理攻击强度及风险参数。
- **主指标固定：** `e_t=||deployed_theta(t)-clean_shadow_theta(t)||_2`；在攻击后首采样`e_44>0.001`的前提下，往后`e_t≤0.001`连续20点才为“经验纠正”。对于初始未离开容差者标记`not at risk`、不得计入攻击后纠正成功；所有种子必须保留用于物理代价与完整性分母。成功需同时报告 `initial_outside`、`genuinely_corrected`。
- 新v3的离线动态干净影子 **也采用与v3相同的锚点近端正则化更新算子**，保持模型含义一致；因此只能判为“新机制本身的同算子干净反事实经验纠正”，**不能当成旧无正则化策略的恢复**。
- 独立原生审计逐种子重算误差、全部相邻和10步窗口、代理偏差、更新接受、物理归一化L1、控制L2、采样安全越界。未观察到物理状态从恢复集外返回就不得报告物理故障恢复速度；采样零越界不代表G5连续时间不变性。
- PR与原560回合主实验保持只读。正常场景验证零误差，不当成攻击后纠正。
- 独立确认结果如不支持探索结论，不能在80–119上修改门限/机制再把同一批种子称为确认；应将该40种子确认为失败结果，未来改进采用新的独立确认种子。

## 压力测试严格独立于确认
协同投毒（两名受控客户端合谋）、持续观测偏置（破坏延长到第180步）和检查点故障/篡改的试验，必须在**另一压力分支和另外的探索种子（例如64–71）**进行。所有压力测试要记录攻击注入和失败；不得根据这些压力测试回改本冻结版并继续宣称同一80–119集的“纯确认”。压力破坏超出先前保证的假设时，报告其失效边界而非对抗全部无条件鲁棒性。

## 检查和可追溯性
- 确认工作流每个原生作业先通过git对象SHA检验；SHA不匹配立即失败。
- 每个分片生成包含完整原始JSONL、`summary.csv`、`manifest.json`的不可变归档和SHA256；独立审计必须先验证12份档案的哈希、任务全部480个回合、每回合480点，无遗漏。
- Holdout Github Actions run、commit SHA、完整JSONL、失败和审计生成物将保留为可复核证据。
