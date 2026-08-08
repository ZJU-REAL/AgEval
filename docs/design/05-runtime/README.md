# 05 — Runtime（索引）

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本目录与同级其它 design 文档共同构成设计权威**（自包含） |
| 摘要 | Runtime 稳定机制：Lifecycle、Provider/L1、Agent Service（ACP）、Environment、Evaluation、Evidence、Campaign/Suite。 |

> **兼容入口：** 历史路径 [`../05-runtime-core.md`](../05-runtime-core.md) 为 stub，正文在本目录。

---

## Runtime 职责边界

Runtime Core 保留 Harness 无法可靠强制的外部职责：

- Run、Trial、Attempt 和 Invocation identity；
- Provider、container、process、mount 和 workspace lifecycle，以及高隔离档的 UID/GID；
- Agent Provider invocation、credential projection 和外部成本边界；
- network、secret、path 和 resource capability；
- 数据库、Browser、VM 等 Environment 的 prepare、action 和 teardown，以及按需 reset/freeze/getter；
- declared Artifact 的 publish registry 与内部 materialization；
- writer barrier、独立 evaluator、hidden material 和结果绑定；
- wall time、memory、process、Agent invocation 和外部 action ceiling；
- Runtime、Harness、Evaluation 和 Cleanup 事实的分离；
- **Attempt evidence 与 Agent 轨迹落盘**（观察复盘与轨迹训练的数据源；见 [evidence.md](evidence.md)）。

Runtime 不解释 Retail action、AgentVerse memory、MARBLE branch、Planner、Reducer 或 Tool 业务名称。

## 与 Core 其它组的关系

| Core | Runtime 如何协作 |
| --- | --- |
| Core 1 Config | 消费 `LockedTaskConfig`；运行中不热更新 |
| Core 2 Lifecycle | Run Coordinator 拥有外层状态机（本目录 [lifecycle.md](lifecycle.md)） |
| Core 3 Provider | 物理隔离与投影（[provider-l1.md](provider-l1.md)） |
| Core 4 Capability | Agent / Env / Workspace / Artifact 面由 Runtime 注入 |
| Core 5 Evaluation | barrier 后绑定扁平 Result（[evaluation.md](evaluation.md)） |

Application 层拥有 CLI 与 Campaign 调度；Harness 拥有 Attempt 内业务 loop。两类 scheduler **不合并**。

## 子文目录与阅读顺序

按**设计上的执行链**阅读：

```text
lifecycle
  → provider-l1
  → agent-service（ACP + entry）
  → environment（按需）
  → evaluation
  → evidence
  → campaign-suite（外层编排，与单 Attempt 正交）
```

| 文件 | 稳定设计内容 |
| --- | --- |
| [lifecycle.md](lifecycle.md) | Run Coordinator、三段路径、外层状态机、不变量 |
| [provider-l1.md](provider-l1.md) | Provider、Docker L1 镜像/BOM、多 Actor isolation |
| [agent-service.md](agent-service.md) | Agent Service、**ACP 唯一 coding-agent 入口**、插件扩展、归一化契约 |
| [environment.md](environment.md) | Environment prepare / action / teardown |
| [evaluation.md](evaluation.md) | Workspace/Artifact、Evaluator barrier、Result 绑定 |
| [evidence.md](evidence.md) | Attempt evidence 树与 trajectory 契约 |
| [campaign-suite.md](campaign-suite.md) | Campaign matrix vs Suite task 轴 |

## 文档原则

本目录写的是 **稳定设计方案**，不是实现进度板。

| 应写 | 不应写 |
| --- | --- |
| 机制契约、边界、红线、配置形状 | 「目前处于 xx 状态」「迁移完成前仍…」 |
| 设计内的非目标 / 明确不做 | Issue 勾选、证据等级日报 |
| 模块应有的结构 | 「Current residual 代码可能仍…」 |

实现是否跟上 → **GitHub Issues + 代码 + `examples/`**。[ARCHITECTURE.md](../../../ARCHITECTURE.md) 描述实现结构地图（current vs target 树），不把 design 写成 changelog。
