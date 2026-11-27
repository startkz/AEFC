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
