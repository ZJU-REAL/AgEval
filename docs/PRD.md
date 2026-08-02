# BORA Product Requirements

| 字段 | 值 |
| --- | --- |
| 产品名 | **Bounded Orchestration for Runtime Agents**（**BORA**） |
| 代际 | v2 greenfield |
| 设计权威 | [README.md](README.md) 与 [design/](design/) |
| 状态 | 设计已定稿于仓库 docs；实现按 Core Roadmap 推进 |

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
| 实验操作者 | （后续）Campaign / matrix 批量 Trial |

## 4. 成功标准

1. **精简作者面：** 主要面对一份 `bora.yaml`、Harness 入口、Evaluator 入口与少量 Capability。  
2. **可拓展：** 隔离档、Environment、transport 可增强，不要求 task 预配全集。  
3. **泛化转换：** 同一 owner map 与 evaluator barrier；shared Adapter 通用性由第二领域证明。  
4. **可复盘：** 一次 Trial 的参数、envelope、隔离档与 evaluator 输入可锁定、可比较。  

度量优先：**可转换覆盖面与单次转换成本**，不是示例个数。

详细红线、可见性与非目标见 [design/00-overview-and-product.md](design/00-overview-and-product.md)。

## 5. 能力地图（对齐 Core）

| 层 | 能力 |
| --- | --- |
| **BORA Core** | Config `load_and_lock`；Run/Trial/Attempt；Provider 隔离；Capability API；Evaluator barrier + 结果绑定；**可见性投影** |
| **Harness Core** | 可选 SDK：`HarnessContext`、AgentSession、Tool/Guard、workflow helpers |
| **Harness（package）** | 业务 workflow、本地 Tool、upstream bridge |
| **Application** | CLI、Campaign/matrix（按 Roadmap）、内置/插件 Adapter |

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

整体设计已定，**不按「探索式螺旋试错」规划版本**。Roadmap 以 **BORA Core / Harness Core** 表面为轴稳步推进；每项交付仍对应可验证的工程结果（见 [../specs/ROADMAP.md](../specs/ROADMAP.md)）。实现期若你指定新的绑定决策，再写入 `specs/constitution/`。
