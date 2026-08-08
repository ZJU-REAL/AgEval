# BORA Product Requirements

| 字段 | 值 |
| --- | --- |
| 产品名 | **Bounded Orchestration for Runtime Agents**（**BORA**） |
| 代际 | v2 greenfield |
| 设计权威 | [README.md](README.md) 与 [design/](design/) |
| 状态 | 设计已定稿于仓库 docs；增量实现与验收跟踪见 GitHub Issues |

## 1. 一句话定义

BORA 是 **Harness 的外层编排运行时**：在统一的配置锁定、物理边界、Capability 与独立评测下，运行 task-local 或 upstream Agent Harness，并产出可比较、可复盘的结果。

设计口令：**边界硬、契约薄、实现可胖**。

## 2. 问题

Agent Benchmark 在 loader、loop、Tool、Environment、workspace、evaluator 上差异极大。若每接一个 Benchmark 就在 Runtime 加 task-aware 分支或第二套 workflow 引擎，平台不可维护。

BORA **统一**实验的准备、运行、评测、存证与清理；**不统一** Benchmark 内部如何组织 Agent 与数据流——那属于 package 的 `harness.py` 或 upstream Framework。

## 3. 用户与 Jobs

| 角色 | Job |
| --- | --- |
| 转换者 / 研究员 | 上游 task → BORA package，少改 workflow，自动评测 |
| Harness 作者 | Capability API 写业务 loop，不碰 Docker/credential/verdict |
| 平台维护者 | 薄 Core + 可替换 Adapter，拒绝 Benchmark 名分支 |
| 实验操作者 | Campaign / matrix 批量 Trial |
| 观察 / 训练消费者 | 从一次 Attempt 的**落盘轨迹**复盘 Agent 行为，并导出用于轨迹训练 / 离线分析 |

## 4. 成功标准

1. **精简作者面：** 主要面对一份 `bora.yaml`、Harness 入口、Evaluator 入口与少量 Capability。  
2. **可拓展：** 隔离档、Environment、transport 可增强，不要求 task 预配全集。  
3. **泛化转换：** 同一 owner map 与 evaluator barrier；shared Adapter 通用性由第二领域证明。  
4. **可复盘：** 一次 Trial 的参数、envelope、隔离档与 evaluator 输入可锁定、可比较。  
5. **可落盘轨迹：** 每次真实 Agent invocation（及 Runtime 边界上的关键 effect）在 Attempt evidence 目录中落盘为稳定、可解析的文件（默认 JSONL + 归一化摘要）；`Result.logs` 指向该树；轨迹**不是** PASS 来源，但**是**产品交付物。  

度量优先：**可转换覆盖面与单次转换成本**，不是示例个数。轨迹可用性是独立成功标准：没有 invocation 落盘，不算完整产品路径。

详细红线、可见性与非目标见 [design/00-overview-and-product.md](design/00-overview-and-product.md)。  
轨迹与 evidence 布局见 [design/05-runtime/evidence.md](design/05-runtime/evidence.md)。

## 5. 能力地图（对齐 Core）

| 层 | 能力 |
| --- | --- |
| **BORA Core** | Config `load_and_lock`；Run/Trial/Attempt；Provider 隔离；Capability API；Evaluator barrier + 结果绑定；**可见性投影**；**Attempt evidence / Agent 轨迹落盘** |
| **Harness Core** | 可选 SDK：`HarnessContext`、AgentSession、Tool/Guard、workflow helpers |
| **Harness（package）** | 业务 workflow、本地 Tool、upstream bridge |
| **Application** | CLI、Campaign/matrix、内置/插件 Adapter |

## 6. 非目标（近端）

- 开放插件商店 / 跨组织 Registry  
- Core 内通用 Graph / Handoff / BranchAuthority 平台  
- 默认 durable/reopen 与全局 dashboard（未列入当前 Core 交付前不承诺）  
- 按 Benchmark 名的 Core 分支  
- 兼容 v1 lock / package.manifest / SDK  
- 把事后 token/cost 宣称为执行前硬顶（除非 Provider 支持 reserve）  

## 7. 命名

| 项 | 值 |
| --- | --- |
| 全称 | Bounded Orchestration for Runtime Agents |
| 简称 | BORA |
| 归档 v1 旧称 | Benchmark Orchestration Runtime Architecture |
| CLI（计划） | `bora` |

## 8. 交付方式

整体设计已定，**不按「探索式螺旋试错」规划版本**。按 **BORA Core / Harness Core** 表面稳步推进；增量交付与验收跟踪在 [GitHub Issues](https://github.com/ffy6511/BORA/issues)。绑定决策写入 `docs/design/` 或根 [AGENTS.md](../AGENTS.md) 红线，不另起 Spec 工作区。
