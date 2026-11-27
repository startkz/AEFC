# IEEE39 Bus16 故障与全网物理拓扑证据审计（2026-11-27）

## 1. 当前结论

- Bus16_1 原生三相故障 pilot 已满足预注册恢复集暴露条件，并在故障清除后满足 20 点恢复保持判据。
- 严格执行模式下 AEFC-Full 的额外 Pref 修正为零、执行放行为零、备用动作调用为零；原生 Governor 路径保持不变。
- AEFC-Full 与 Supervisor-only 的配对物理轨迹逐点一致。因此该 pilot 验证严格拒绝行为及原生系统响应，**不证明 AEFC 带来物理恢复增益**。
- 123 个母线物理端口到组件端口的结构拓扑映射已全部解析；但 Simscape 的 I1/I2 等电流序列与 LConn/RConn 的逐项对应仍待当前电流工件交叉核验。
- 完整 IEEE39 在线可观测性、支路热限、非线性 DAE 可达管、连续采样间安全和 Governor 备用可行性均未认证。

## 2. Bus16_1 严格故障 pilot

最新复核运行：[GitHub Actions 45921838661](https://github.com/startkz/AEFC/actions/runs/45921838661)。

运行条件：
- 原生 MathWorks R2024b IEEE39BusSystem 派生模型；
- Bus16_1 三相故障，5.0–5.1 s，故障参数与协议冻结值一致；
- 采样周期 1/60 s，仿真至 8 s；
- AEFC-Full 与 Supervisor-only，种子 0、1；
- 恢复判据：全部 41 个物理母线电压区段相对故障前基线偏差不超过 5%，且 10 台机组归一化转速偏差不超过 0.25，连续保持 20 点。

实测结果（四个 episode）：
- 39 个逻辑母线、41 个物理电压区段、10 个机组转速通道；
- 126 个原生线路/变压器电流序列；Bus16–Bus17 相邻线路保留三相电流轨迹；
- Bus16 故障期间最大母线相对电压偏差约 0.999944；
- 10 台机组最大归一化转速偏差约 0.446705；
- Bus16–Bus17 相邻线路故障期间最大电流约 7.115 kA，故障前约 0.781 kA，故障后窗口约 2.258 kA；
- 故障电流最大值约 18.136 kA；
- 四个 episode 均在 7.1833 s 首次满足 20 点恢复保持，距故障清除约 2.0833 s；
- AEFC-Full 每个 episode 有 470 次内部 adaptation accepted 记录，但执行放行 0 次、备用动作 0 次、额外 Pref 修正最大值 0；
- AEFC-Full 与 Supervisor-only 的母线电压、10 机转速、B16–B17 电流、原生 Pref 和实际交付 Pref 轨迹逐点一致；
- 种子 0 与 1 的物理轨迹也逐点一致。

这些结果说明故障确实造成恢复集暴露，原生系统在故障清除后恢复；由于严格执行没有释放额外控制，不能将该恢复归因于 AEFC。

## 3. 十种子确认实验

正式确认运行：[GitHub Actions 45924335524](https://github.com/startkz/AEFC/actions/runs/45924335524)。

- 预留种子 80–89；
- 两种方法、相同 Bus16_1 故障、相同恢复判据；
- 20 个配对 episode；
- 审计同时比较方法内配对轨迹与跨种子物理轨迹。

**统计边界：** 当前协议没有把种子注入原生物理扰动；种子只改变控制器离线客户端数据生成。若物理轨迹仍逐点相同，则该实验只能作为十种子可重复性确认，不能把十个 seed 作为十个独立物理随机样本，也不能计算 AEFC 物理恢复效果的显著性。

## 4. 32-case 持续 Pref 压力 pilot

运行：[GitHub Actions 45920180021](https://github.com/startkz/AEFC/actions/runs/45920180021)。

- 32 个 episode，AEFC-Full 与 Supervisor-only 配对；
- 压力幅度 0.024、0.06、0.12、0.24；
- 10 台机组最大归一化转速偏差最高约 0.169514；
- 恢复集边界为 0.25；
- 32 个 episode 均未在攻击结束时越界，真正恢复事件为 0。

该实验不构成物理恢复实验。不得在观察结果后直接扩大攻击幅度并将其并入原预注册协议；如需新的压力边界标定，应单独预注册，并加入母线电压、支路电流和变压器绕组电流约束。

## 5. 123 个母线端口到组件端口的结构映射

已完成的物理连接句柄工件：[GitHub Actions 45772532158](https://github.com/startkz/AEFC/actions/runs/45772532158)。

| 项目 | 结果 |
|---|---:|
| 物理母线区段/母线块 | 41 |
| 母线物理端口 | 123 |
| 已匹配端口 | 123 |
| 未解析端口 | 0 |
| 唯一输电线路组件 | 34 |
| 唯一变压器组件 | 12 |

端口映射基于 Simulink/Simscape 物理端口句柄及其父/子连接线，不是根据母线编号推断。123 个母线端口还连接到 19 个负荷块、10 个发电机块、一个三相故障块及 Bus16/Bus26 分段母线互连。

有五个物理端口出现多组件连接：Bus16_1、Bus16_2、Bus26_1、Bus26_2 的分段母线互连，以及 Bus16_1/RConn1 同时连接 B16–B17 和三相故障支路。不能把这些端口按简单的一端口一组件关系处理。

当前映射工件明确将 `I#` 到 `LConn/RConn` 的电流变量映射标记为未验证。不得仅根据端口顺序把 `I1`、`I2` 等标签写成已验证的组件电流身份。

## 6. 电流通道的异常与当前核验

已完成的 Simscape 全量 Series 清点确认：
- 39 个逻辑母线电压通道、41 个物理电压区段；
- 34 条输电线路、102 个线路电感电流幅值序列；
- 12 台变压器、24 个绕组电流序列；
- 共 126 个选定支路电流序列。

**必须保留的异常：** 现有清点中所有线路的 `inductor_a/i/amplitude` 最大值接近数值零（约 1.17e-12 至 5.59e-11 A），而 `inductor_b` 与 `inductor_c` 非零且幅值相近。不能把 102 个系列未经核验就统称为有效三相线路电流。

当前新运行 [45924972310](https://github.com/startkz/AEFC/actions/runs/45924972310) 正在保存 123 个母线端口电流与 126 个支路电流的原始序列，并补充模型端口连接元数据。后续将交叉核对：
1. 每个 Bus 块的 `I#` 序列与物理端口索引；
2. 34 条线路的 a/b/c 相电流是否均有合理非零响应；
3. 12 台变压器的 `i1/i2` 绕组电流与两侧母线端口对应关系；
4. Bus16/Bus26 分段连接处的电流守恒与端口归属。

## 7. 论文写回边界

当前可以写入的结论：
- Bus16_1 三相故障在冻结判据下真实造成恢复集暴露；
- 故障清除后，原生 Governor/系统响应满足采样恢复判据；
- 严格模式拒绝了所有额外 Pref 修正，AEFC-Full 与 Supervisor-only 的物理轨迹一致；
- 123 个母线物理端口到 34 条线路和 12 台变压器的结构拓扑映射已完成；
- Simscape 电流变量与端口的逐项对应仍在核验。

当前不能写入的结论：
- AEFC-Full 在该 Bus16 pilot 中提高了物理恢复性能；
- 四个在线转速观测代表完整 IEEE39 状态；
- 所有 123 个 `I#` 通道已完成可信在线测量认证；
- 已证明全网支路热安全、连续时间安全或应急 Governor 可行性。

**发布决策：** 在十种子确认审计和 I# 电流变量映射审计完成之前，只更新证据边界和限制，不把该 pilot 写成 AEFC 的物理恢复增益实验。




## 8. Final 123-port physical and current-variable map

The terminal-signature join [Actions run 45928276856](https://github.com/startkz/AEFC/actions/runs/45928276856) resolves all 123 physical Busbar ports to the native Simscape current-variable series. The independent original-model rebuild [Actions run 45928516528](https://github.com/startkz/AEFC/actions/runs/45928516528) also confirms 41 Busbar blocks, 123 physical ports, 34 lines, 12 transformers, and the same interleaved candidate formula. The empirically supported ordering is interleaved:

I_(2k-1) = LConn_k; I_(2k) = RConn_k.

This differs from both the local-index and global PortConnectivity-order assumptions. Across 41 Busbar blocks, the predicted interleaved I# set matches the captured current-series set exactly. The interleaved rule yields 65/70 exact bus-port-to-line-terminal matches, compared with 33/70 under global PortConnectivity order and 24/70 under the previous local-index candidate. All 65 single-component line-port references match directly. The five remaining references belong to three composite line endpoints.

The 34 lines have 68 terminal-current vectors captured from phase_splitter1/2. Of the 68 unique line component ports, 65 match directly; the three composite endpoints arise from:
- Bus16_1/RConn1, shared by B16-B17 and the three-phase fault;
- B19-B16/RConn1, shared by Bus16_1/LConn2 and Bus16_2/LConn1;
- B25-B26/RConn1, shared by Bus26_1/LConn1 and Bus26_2/LConn1.

The two split-bus current sums are already consistent with the corresponding line terminal current to numerical precision:
- Bus16_1/I3 + Bus16_2/I1 = −(B19-B16 phase_splitter2), normalized residual 1.49e-16;
- Bus26_1/I1 + Bus26_2/I1 = −(B25-B26 phase_splitter2), normalized residual 2.30e-16.

All 24 transformer endpoints are structurally mapped to 12 transformers. Eleven endpoints directly match a winding-current series up to sign/phase permutation; all 24 are consistent with the associated winding current under a fixed three-phase linear transformation. This is a current-signature consistency check, not a transformer protection or thermal certificate.

The earlier near-zero inductor_a/i/amplitude path is an internal inductor-current series, not the line terminal phase-A current. The actual terminal-current vectors are phase_splitter1/2 and contain all three phase components. The remaining Bus16 fault-port sum is being checked using the one-episode fault-current probe.

**Claim boundary:** all 123 physical ports have a current-variable assignment under the validated interleaved ordering. The five composite bus ports require component-sum interpretation; the Bus16 fault composite is still under targeted validation. No online sensor integrity, branch thermal limits, or full-network safety is certified.


## 8. 123 个 Bus/I# 电流变量的端口映射与五个复合节点 KCL 审计

本节更新此前“Bus/I# 到 LConn/RConn 的变量关联待验证”的状态。最新证据来自：

- 物理端口连接映射 v2：[Run 45928516528](https://github.com/startkz/AEFC/actions/runs/45928516528)
- 123 个电流变量与物理端口的交错序号签名匹配：[Run 45928276856](https://github.com/startkz/AEFC/actions/runs/45928276856)
- 全部线路两端与变压器绕组端电流采集：[Run 45926990179](https://github.com/startkz/AEFC/actions/runs/45926990179)
- Bus16_1 故障端口电流探测：[Run 45928384720](https://github.com/startkz/AEFC/actions/runs/45928384720)
- Bus16_1/RConn1 复合电流和独立审计：[Run 45929575893](https://github.com/startkz/AEFC/actions/runs/45929575893)
- 五个复合母线端口统一 KCL 审计：[Run 45930108949](https://github.com/startkz/AEFC/actions/runs/45930108949)

### 8.1 123/123 物理端口的电流变量序号规则

全部 41 个母线物理区段共提取 123 个 Bus/I# 三相电流序列。由 Busbar 块的物理端口顺序和 Simscape 电流向量的签名匹配，得到：

\[
I_{2k-1}\leftrightarrow LConn_k,\qquad I_{2k}\leftrightarrow RConn_k.
\]

- 123/123 个电流变量均映射到物理端口，未解析项为 0；
- 65 个单组件线路端口引用中，65 个三相电流向量均与对应线路端口电流直接匹配，符号和相序一致；
- 34 条线路共采集 68 个端点三相电流向量；
- 12 台变压器共采集 24 个绕组端电流向量。

此前使用的线路内部 `inductor_a/i/amplitude` 序列在 34 条线路上均接近数值零，不能代表完整三相线路电流。后续物理电流分析应采用线路 `phase_splitter1/2/I/instantaneous` 两端三相电流向量。当前 68 个端点向量的 A/B/C 三个相分量均为非零，且单位为 A。

### 8.2 五个多组件母线端口的 KCL 验证

五个复合端口涉及 Bus16、Bus26 分段母线互连和 Bus16_1 故障支路。统一审计使用原始三相电流向量验证以下节点电流和：

| 节点 | KCL 组成 | 归一化残差 | 最大绝对残差 |
|---|---|---:|---:|
| Bus16 分段节点 | Bus16_1/I3 + Bus16_2/I1 + B19–B16 端点2 | 7.41×10⁻¹⁷ | 4.55×10⁻¹³ A |
| Bus26 分段节点 | Bus26_1/I1 + Bus26_2/I1 + B25–B26 端点2 | 6.35×10⁻¹⁷ | 9.24×10⁻¹⁴ A |
| Bus16_1/RConn1 故障节点 | I2 + B16–B17 端点1 + 三相故障电流（5.0–5.1 s） | 9.04×10⁻¹⁷ | 7.28×10⁻¹² A |

因此，五个多组件端口的拓扑连接与复合电流和均有对应证据，不再将它们简单视作单组件端口。故障前窗口中 I2 与线路端电流的残差约为 2.17×10⁻⁴（按参与电流范数之和归一化），反映故障支路未激活时仍存在的小量数值泄漏；故障窗口中则满足三支路电流和。

### 8.3 变压器端电流的证据边界

24 个变压器绕组端电流向量均通过当前采样轨迹上的线性电流向量一致性检查，最大拟合残差约为 1.17×10⁻¹⁴；其中 11/24 个端点为直接符号/相序匹配。其余端点的拟合受变压器相移及平衡三相子空间影响，9 个拟合矩阵的样本秩为 2，不能把这些轨迹拟合解释成对所有可能工况都成立的唯一满秩物理变换。端点拓扑来自物理连接句柄，拟合仅作为离线信号对应性检查。

### 8.4 当前可以和不可以得出的结论

现在可以确认：原生 Simscape 离线日志中 123 个母线端口电流变量与物理端口顺序一致；65 个单组件线路端口具有直接三相签名匹配；五个复合母线端口的 KCL 关系已在原生数据中验证；线路和变压器端点电流均有完整三相日志。

仍然不能确认：这些日志就是可信在线传感器；线路/变压器热额定值已经核实；当前支路电流低于热限；全网电气状态连续安全；或这些离线变量已进入 AEFC 控制器。所有相关安全认证字段仍为 false。完整 IEEE39 执行安全门槛继续保持 BLOCKED。


**审计精化：** [Run 45930232661](https://github.com/startkz/AEFC/actions/runs/45930232661) 在同一组原始工件上增加了变压器拟合秩检查：24 个端点中 11 个为直接符号/相序匹配，24 个均满足样本轨迹线性一致性；其中 9 个拟合为秩 2、15 个为秩 3。该结果明确限制了变压器电流映射的解释范围，不把平衡三相轨迹上的秩 2 拟合当作唯一满秩变换。


## 9. MATPOWER case39 的 46 条支路参考额定值映射

参考数据源固定为 MATPOWER/matpower 的 case39 文件，commit `b6c85b0323d20fb801cab3377c803a285d730847`。拓扑匹配审计 [Run 45931096901](https://github.com/startkz/AEFC/actions/runs/45931096901) 得到：

- 34/34 条 MathWorks 原生输电线路与 MATPOWER case39 的线路端点匹配；
- 12/12 台 MathWorks 原生变压器与 MATPOWER case39 的变压器端点匹配；
- 总计 46/46 个端点对匹配，未匹配项为 0；
- MATPOWER 数据的 baseMVA 为 100 MVA，39 个母线的 baseKV 均为 345 kV；
- RATE_A 参考值分布：500 MVA（7 条）、480 MVA（1 条）、600 MVA（20 条）、900 MVA（14 条）、1000 MVA（1 条）、1200 MVA（2 条）、1800 MVA（1 条）；
- 按 345 kV 计算的 RATE_A 等效线电流范围为约 803.27–3012.26 A RMS。

该映射只建立**支路拓扑和公开参考额定值之间的对应关系**。MATPOWER case39 文件的注释说明其潮流限值来自 PSERC TC Calculator 的修改数据；这些数值不是 MathWorks Simscape 模型自带的热额定值。当前尚未完成 MathWorks 线路 R/X/L/C、变压器绕组额定电压、基准容量、端电流 RMS 定义与 MATPOWER 参数的逐项等价性验证。因此：

1. RATE_A/B/C 暂时只能作为 benchmark reference limits；
2. 不能把 345 kV 等效电流直接用于变压器低压绕组电流比较；
3. 不能用瞬时电流峰值直接与 RATE_A 等效 RMS 电流比较；
4. 在参数等价、绕组电压基准和 RMS 窗口核验完成前，不报告支路热过载率或热安全通过率。

下一项工作是提取 MathWorks 原生线路和变压器掩码参数，逐支路与 MATPOWER 的 per-unit R/X、tap ratio 和 baseMVA 对齐；只有对齐后才进入连续热限比较。


## 10. 原生在线测量端口审计：现有发电机信号与电网测量缺口

原生 MATLAB R2024b 信号端口清点已通过：[Run 45930528000](https://github.com/startkz/AEFC/actions/runs/45930528000)。其原始工件逐项记录了 Busbar、线路、变压器和控制器端口句柄及连接关系。

### 10.1 现有发电机测量候选信号

模型包含 70 个 PS-Simulink Converter，全部位于发电机子系统，没有一个位于 Grid 子系统；另有 60 个 Synchronous Machine Measurement 块和 20 个 Simulink-PS Converter。每台发电机现有以下三个可路由的 Simulink 信号候选：

- 转子电角度：10 路；
- 转子速度：10 路；
- 发电机端电压：10 路。

这些信号由发电机本地测量块和 PS-Simulink Converter 输出，部分连接至 Bus Creator/Unit Delay。它们是可供独立安全监视器使用的模型信号候选，但当前并未作为完整测量向量接入 AEFCNativeController；也没有因此获得可信传感器完整性证明或测量误差界。

当前 AEFCNativeController 仍只有两个顶层输入：四路发电机转速观测 Mux，以及离线攻击/客户端数据包。实际物理观测仍只有四路转速。

### 10.2 Grid 子系统没有现成的在线电压/支路电流信号端口

端口句柄审计发现：

- 41 个 Busbar 块只有 LConn/RConn 物理连接端口，没有信号输出端口；
- 34 个线路块只有物理连接端口，没有 Simulink/PS 测量输出端口；
- 12 个变压器块同样没有可路由的信号输出端口；
- Grid 子系统内没有 PS-Simulink Converter。

因此，39 个逻辑母线电压、41 个物理母线区段电压、68 个线路端点三相电流和 24 个变压器绕组电流，虽然已能从 Simscape 离线日志完整提取，但目前仍不是控制器可接收的在线传感器信号。

### 10.3 下一步传感器接入顺序

建议先复用现有 10 台机组的转速、转子角和端电压信号，构建独立的 Generator Measurement Monitor；随后在 41 个物理母线区段接入电压测量，在 34 条线路两端及 12 台变压器两侧接入电流测量，并将测量信号通过显式转换器接入独立的全网安全监视器。传感器噪声、偏置、丢包、时间同步和完整性保护需要作为单独的威胁模型与实验变量，不得把仿真器隐藏日志直接当作可信在线观测。

这一步只解决测量路径，不自动解决全状态估计、误差界或可达集证明。完整 IEEE39 安全认证仍保持 BLOCKED。


**发电机测量总线补充核验：** [Run 45931515695](https://github.com/startkz/AEFC/actions/runs/45931515695) 确认顶层 Generators 子系统具有一个独立 Simulink Outport，直接连接到 Measurements 子系统的 Inport；Generators 的另一物理端口仍连接 Grid。Measurements 子系统包含 20 个 In Bus Element、两个 10 输入 Mux 和 Scope，没有输出端口，因此它是测量总线的显示/监视终端，不是 AEFC 控制输入。该总线可在 Generators/Measurements 连接处分支，供独立安全监视器使用；其中 20 个字段的准确名称、单位和采样时间仍由 bus schema 探测工作流核验。


### 10.4 原生三相传感器库候选已定位

[Run 45932018570](https://github.com/startkz/AEFC/actions/runs/45932018570) 在 MATLAB R2024b 的 Simscape Electrical 库中找到三相电流、电压测量候选块，包括：

- \`Current Sensor (Three-Phase)\`
- \`Phase Voltage Sensor (Three-Phase)\`
- \`Line Voltage Sensor (Three-Phase)\`
- \`Current and Voltage Sensor (Three-Phase)\`

目前只完成了库块发现和端口句柄枚举。由于 Simscape 物理信号端口在块句柄中也表现为连接端口，不能仅根据 \`LConn/RConn\` 名称判断其类型。正在通过实际连接 \`nesl_utility/PS-Simulink Converter\` 的小模型探测，确认每种传感器的物理信号输出端口和三相向量形式。确认后先在 Bus16_1 和 B16–B17 做单点插装，再验证测量值与现有离线 Simscape 日志一致，最后才扩展到全网。
