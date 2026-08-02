# BORA Roadmap — Core 交付计划

整体设计已定稿于 [`docs/design/`](../docs/design/)。本路线图**不以探索式螺旋试错为主轴**，而以 **BORA Core** 与 **Harness Core** 表面为交付单元，按依赖稳步实现。版本号仅用于索引与验收勾选；语义以 Core 名称与设计文档为准。

## 维护规则

- 设计变更先改 `docs/design/`，再改本文件与 Active Spec。  
- Version Index 勾选表示该版本约定验收通过。  
- 一个 Active Spec 可覆盖相邻版本，但 Index 仍按版本分别勾选。  
- Adapter 按协议/资源/机制命名；禁止 Benchmark 名分支。  
- `specs/constitution/` 不写完整设计，仅记录你指定的实现期决策。  
- v1 编号与完成态不继承。  

## 依赖总览

```text
Config (v0.1)
  → Lifecycle (v0.2)
      → Provider L0 (v0.3)
          → Capability (v0.4)
              → Harness Core HC-1 (v0.5)
                  → Evaluation + bora run 竖切 (v0.6)
                      → Harness Core 加厚 (v0.7)
                      → Provider L1 隔离 (v0.8)
                          → 插件 AgentExecutor (v0.9)
                          → Environment 资源 (v0.10)
                          → Campaign/matrix (v0.11)
                          → 后台/耐久 (v0.12，按需)
```

## 版本索引

- [ ] `v0.1` — BORA Core 1：Config（load_and_lock + Package）
- [ ] `v0.2` — BORA Core 2：Lifecycle（Run / Trial / Attempt）
- [ ] `v0.3` — BORA Core 3：Provider L0
- [ ] `v0.4` — BORA Core 4：Capability API
- [ ] `v0.5` — Harness Core 1：entrypoint + HarnessContext
- [ ] `v0.6` — BORA Core 5 + APP 竖切：Evaluation 与真实 `bora run`（Codex）
- [ ] `v0.7` — Harness Core 2–3：AgentSession / Tool·Guard 软限
- [ ] `v0.8` — Provider L1：隔离强化（Docker、credential、writer barrier）
- [ ] `v0.9` — 插件化 AgentExecutor（第二后端）
- [ ] `v0.10` — Environment Capability 最小真实资源
- [ ] `v0.11` — Campaign / 实验矩阵
- [ ] `v0.12` — 后台控制与耐久 authority（按需）

## v0.1 — BORA Core 1：Config

### 目标

Config Core 成为 `bora.yaml` 的唯一规范读取者，并提供可验证的 `load_and_lock`。

### 设计

- [02 Task Package 与 Config](../docs/design/02-task-package-and-config.md)
- [01 BORA Core](../docs/design/01-bora-core.md)
- [Spec 00](active/00-core-batch0-and-batch1-plan.md)

### 关键交付

- [ ] 工程骨架（与本版本同批或紧邻 Spec 交付）
- [ ] Package 布局与 task 定位
- [ ] `load_and_lock` 与非法配置 fail-closed
- [ ] lock/inspect 用户可调用路径

### 验收标准

- [ ] 合法 example package 可 lock 并得到可复盘摘要
- [ ] 未知 task / 缺字段失败
- [ ] 工程门禁与 docs 同步

### 后续 TODO

- [ ] `v0.2`：Lifecycle Core

## v0.2 — BORA Core 2：Lifecycle

### 目标

Runtime 拥有 Run / Trial / Attempt 身份与 prepare→run→evaluate→cleanup 外层顺序。

### 设计

- [05 Runtime Core](../docs/design/05-runtime-core.md)

### 关键交付

- [ ] 稳定 identity 与 Attempt 状态机
- [ ] retry 创建新 Attempt
- [ ] 超时/取消进入统一 cleanup 路径

### 验收标准

- [ ] 生命周期顺序与 identity 有自动化证明
- [ ] 与 LockedTaskConfig 衔接

### 后续 TODO

- [ ] `v0.3`：Provider L0

## v0.3 — BORA Core 3：Provider L0

### 目标

提供 L0 process 级运行位置与基础 workspace 边界，并记录实际 assurance 档。

### 设计

- [05 Provider](../docs/design/05-runtime-core.md)
- [06 可见性](../docs/design/06-capability-adapter-visibility.md)

### 关键交付

- [ ] Local process Provider
- [ ] 最小 workspace / workdir 约定
- [ ] Result 元数据记录 assurance

### 验收标准

- [ ] Attempt 可在 L0 下为后续 harness 启动提供边界

### 后续 TODO

- [ ] `v0.4`：Capability
- [ ] `v0.8`：L1 隔离

## v0.4 — BORA Core 4：Capability API

### 目标

向 Harness 注入 Attempt 范围的 Capability；未授权效果执行前拒绝。

### 设计

- [01 §2.6](../docs/design/01-bora-core.md)
- [06 Capability](../docs/design/06-capability-adapter-visibility.md)

### 关键交付

- [ ] `HarnessContext` 契约面（Runtime 侧）
- [ ] agent/environment/workspace/artifacts/params/events 最小实现边界
- [ ] 关闭 Capability 与 writer stop 挂钩点

### 验收标准

- [ ] Harness 仅经 Capability 触达外部效果
- [ ] 未授权 action fail-closed

### 后续 TODO

- [ ] `v0.5`：Harness Core SDK

## v0.5 — Harness Core 1：entrypoint 与 Context

### 目标

约定 harness entrypoint，并通过 `ctx.params` 提供只读 parameter view。

### 设计

- [04 Harness Core SDK](../docs/design/04-harness-core-sdk.md)
- [03 Harness 层](../docs/design/03-harness-layer.md)

### 关键交付

- [ ] `bora_sdk` 最小包
- [ ] entrypoint 加载约定
- [ ] example harness 可读 params

### 验收标准

- [ ] Runtime 可启动 example harness 并注入 context

### 后续 TODO

- [ ] `v0.6`：Evaluation + `bora run`
- [ ] `v0.7`：SDK 加厚

## v0.6 — BORA Core 5 + 首条 `bora run` 竖切

### 目标

打通 Evaluation barrier 与生产入口：真实 Codex 路径下 `bora run` 产出独立 verdict 与 evidence。

### 设计

- [07 Evaluation](../docs/design/07-budget-evaluation-failure.md)
- [05 Evaluator / Result](../docs/design/05-runtime-core.md)

### 关键交付

- [ ] Evaluator runner + 扁平 Result
- [ ] evidence 目录；secret 不入证
- [ ] 内置 Codex AgentExecutor
- [ ] CLI `bora run` 成功/失败路径

### 验收标准

- [ ] Success：真实 Codex + 独立 evaluation + evidence path
- [ ] Expected failure：未知 task 在 Agent 前失败
- [ ] `completed` 不自动成为 PASS
- [ ] 工程门禁通过

### 后续 TODO

- [ ] `v0.7`：Harness Core 加厚
- [ ] `v0.8`：L1 隔离

## v0.7 — Harness Core 2–3：Session 与 Tool 软限

### 目标

提供 AgentSession 薄封装与 ToolSet/CallLimit 软限，硬顶仍在 Runtime。

### 设计

- [04 §7.5–7.8](../docs/design/04-harness-core-sdk.md)

### 关键交付

- [ ] AgentSession 辅助
- [ ] ToolSet / CallLimit（parameters 驱动）
- [ ] 示例多步 harness 回归

### 验收标准

- [ ] 软限可测；硬顶路径不被 SDK 绕过

### 后续 TODO

- [ ] `v0.9`：第二 Agent 后端时复用同一 Harness API

## v0.8 — Provider L1：隔离强化

### 目标

Docker（或等价）Attempt、credential 投影、hidden material 不 mount、writer barrier 与 clean evaluator 材料分离。

### 设计

- [05 Provider](../docs/design/05-runtime-core.md)
- [08 安全](../docs/design/08-conversion-security-testing.md)

### 关键交付

- [ ] 隔离 Attempt
- [ ] scoped credential 投影
- [ ] evaluator-only 与 Agent 材料分离

### 验收标准

- [ ] 负向：篡改/泄露类在 invocation 前失败
- [ ] 既有 `v0.6` 公开路径在 L1 下仍可复现（或文档化差异）

### 后续 TODO

- [ ] `v0.10`：有状态 Environment

## v0.9 — 插件化 AgentExecutor

### 目标

通过配置选型第二 AgentExecutor（entry point 或等价注册），未知 executor fail-closed。

### 设计

- [06 插件](../docs/design/06-capability-adapter-visibility.md)
- [05 Agent Service](../docs/design/05-runtime-core.md)

### 关键交付

- [ ] Agent Service 注册/选型
- [ ] 第二 Executor 最小实现或插件样例
- [ ] credential 按 executor 投影

### 验收标准

- [ ] 配置切换后端的可运行路径
- [ ] 未知 executor 拒绝

### 后续 TODO

- [ ] Research：更多后端仅在有真实需求时立项

## v0.10 — Environment Capability 最小真实资源

### 目标

至少一种资源类型 Adapter；业务 action 留在 package；shared 路径无 Benchmark 名分支。

### 设计

- [05 Environment](../docs/design/05-runtime-core.md)
- [08 转换与通用性](../docs/design/08-conversion-security-testing.md)

### 关键交付

- [ ] Environment capability + 一种资源 Adapter
- [ ] package 内 service/action
- [ ] teardown 有界

### 验收标准

- [ ] 有状态公开 journey + 负向未授权 action
- [ ] Adapter 命名与扫描符合设计

### 后续 TODO

- [ ] `v0.11`：批量 Trial

## v0.11 — Campaign / 实验矩阵

### 目标

前台串行多 Trial 与确定性配置矩阵比较（Application 层）。

### 设计

- [05 Campaign](../docs/design/05-runtime-core.md)

### 关键交付

- [ ] Campaign 串行调度
- [ ] matrix expand + 可重建比较摘要

### 验收标准

- [ ] ≥2 Trial 独立 result
- [ ] 非法 trial 引用 fail-closed

### 后续 TODO

- [ ] `v0.12`：后台与耐久（仅当需要）

## v0.12 — 后台控制与耐久 authority

### 目标

在明确需求下提供跨进程 status/cancel 与有限耐久 authority（范围由实现 Spec 收窄）。

### 关键交付

- [ ] 后台控制最小面
- [ ] 耐久范围与恢复门禁（若做恢复则同批或紧邻 Spec）

### 验收标准

- [ ] 控制路径与失败语义可演示
- [ ] 不破坏既有前台 Core 路径

### 后续 TODO

- [ ] Research：远程 worker（未立项则保持 open Research）
