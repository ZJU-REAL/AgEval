# BORA Glossary

定义以 [design/](design/) 为准；本表为统一短定义。

| 术语 | 定义 |
| --- | --- |
| **BORA** | Bounded Orchestration for Runtime Agents；Harness 外层编排运行时 |
| **BORA Core** | 外层五组机制：Config、Lifecycle、Provider、Capability、Evaluation |
| **Harness Core** | 可选 Python SDK（`HarnessContext` 等）；可被 upstream 替代；无 Run/verdict authority |
| **Harness** | package 内 workflow（`harness.py`）或 upstream Framework 入口 |
| **Task Package** | `bora.yaml` + Harness 入口 + evaluation + 可选 lib/assets |
| **`bora.yaml`** | 单一规范 task 配置：parameters + 外部 envelope |
| **`load_and_lock`** | Config Core 原子入口 → `LockedTaskConfig` |
| **LockedTaskConfig** | 一次 Trial 可复盘的锁定配置 |
| **HarnessTerminal** | Harness 结束信号；`completed` ≠ PASS |
| **Capability** | Attempt 内已授权操作面：agent、environment、workspace、artifacts… |
| **Adapter / Plugin** | Capability/Provider 的实现；entry point 可分发 |
| **Agent Service** | 主仓调度面：选型 AgentExecutor |
| **AgentExecutor** | 具体 Agent 后端（Codex CLI、Pi invoke 等） |
| **Provider** | 物理运行时与隔离（process/container、mount、network、secret） |
| **可见性投影** | 消费者受限视图（path/secret/network/params/materialize） |
| **Run / Trial / Attempt** | 外层执行身份；retry → 新 Attempt |
| **Evaluator** | task-local 真值所有者 |
| **Evaluator barrier** | stop writers → materialize → evaluate → bind |
| **Campaign** | 多 Trial 调度（Application 层） |
| **硬顶 / 软限** | 硬顶 Runtime 强制；软限在 parameters 内由 Harness 使用 |
| **assurance** | 隔离档位（L0/L1/L2…）；Result 记录实际档位 |
