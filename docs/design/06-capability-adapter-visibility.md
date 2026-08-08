# 06 — Capability、Adapter 插件与可见性

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | Capability 契约、可分发插件、Adapter 准入、文本/文件/多 Agent 可见性投影。 |

---

## 9. Core 的扩展边界：Capability 与 Adapter

### 9.1. Capability

Capability 是 Runtime 向本次 Attempt 暴露的受限操作面，例如：

- Agent invocation；
- Environment binding 和 action；
- WorkspaceView；
- Artifact publish/materialize；
- Event sink。

MVP 的 Capability 是进程内对象。未来可以由 JSONL bridge、stdio 或 scoped socket 承载同一 contract，Harness 不感知 transport。

### 9.2. Adapter 与可分发插件

Adapter 实现具体协议、资源类型或执行机制。用户可按 [Agent Service 扩展模型](05-runtime/agent-service.md) **自研并分发**，不限于官方清单，例如：

- Docker Provider；
- **Agent Executor 插件**：实现 `AgentExecutor`（见 [05-runtime/agent-service.md](05-runtime/agent-service.md)），经 `bora.agent_executors` 注册。**内置：** `acp`（单一 client + entry registry，含 Mode 1 `pi-acp` 等）、`openai-http`；**不是**每个 vendor 私有 stdout 各写一套 Core parser。第三方可分发其它 mechanism kind，但须 fail closed、不得静默替换已 lock 的 entry；
- Environment 资源实现：MySQL / PostgreSQL / Browser / VM…；
- Filesystem Artifact materializer。

**优先鼓励用户定制的是「实现 Core 已开放契约的插件包」**；Agent invoke 只是其中最常举例的一面。实现内部可用 protocol/Port，但 Port 不是 package 作者必学层。Actor、Context、Tool、Router 和 Join 是 Harness 概念，不自动变成 Core 插件 API。

### 9.3. Adapter 准入

新增 Adapter 前要回答：

1. 它实现的协议、资源或执行机制是什么？
2. 它能否只根据 capability config 和调用参数工作？
3. 是否需要读取 Benchmark、task、角色或业务 action 才能选择逻辑？
4. 它是否拥有独立 lifecycle、失败和 cleanup？
5. 普通 Python callable 或已有 capability 是否已经足够？

第 3 项为“需要”时，逻辑应留在 Task Package。第 5 项为“足够”时，不新增 Adapter。

### 9.4. 带 lifecycle 的 component

需要独立进程、健康状态和 lifecycle 的资源，在 Environment 或 Provider 中声明为 component，例如 Attempt-local database、Browser server 或 upstream API server。Service 只是这类 component 的实现描述，不形成第四层公共抽象。

```text
resolve runtime identity
  → create isolated process/container
  → bind resource and network
  → healthcheck
  → expose scoped capability
  → stop writers / optional freeze
  → teardown
```

Task-local Python class、闭包、Context、计数器和 Router 不升级为 component。

## 10. Context、文件与多 Agent 可见性

### 10.1. 文本上下文

Harness 或 upstream Framework 管理：

- Agent 输入输出；
- Environment observation；
- team memory；
- receiver routing；
- speaker selection；
- prompt projection；
- summary 和 compaction。

如果 Agent 只通过 BORA Agent capability 接收 prompt，Harness 已经决定模型看到的文本。Agent 还拥有 terminal、filesystem 或 network 时，需要叠加 Provider capability。

### 10.2. 普通 Agent 间传递

同一 Harness 内的数据可以按最轻的方式传递：

1. 同一函数调用：Python value；
2. 同一 Harness 进程：dataclass、Pydantic model 或 JSON-compatible object；
3. 同一 workspace：相对文件路径；
4. 不同 Agent sandbox：publish declared path，由 Runtime 生成 read-only materialization；
5. Harness 到 evaluator：writer stop 后 materialize `evaluation.inputs`。

普通消息交接不要求 Runtime `HandoffRef`。只有多个独立进程需要 durable、可恢复、可 reopen 的 mailbox 时，才设计专门的 handoff store。

### 10.3. 文件共享

文件共享由 workspace 和 Artifact capability 共同处理：

```text
Writer workspace
  → publish Artifact
  → Runtime 检查 producer 与 path
  → materialize 到 Reviewer inbox
  → Reviewer 获得只读 WorkspaceView
```

两个 Agent 明确共享同一 workspace 时，Harness 可以直接传相对路径。共享 workspace 等于授予相同 filesystem visibility，必须在 `provider.workspace.views` 中明确表达。

`shared-container` 的可写协作还必须受 `provider.agent_isolation.groups[].shared_write` 收紧：路径必须是 workspace-relative、无 `..` / absolute / symlink escape，并落在同 group 参与 actor 的 locked WorkspaceView **write 交集**内。WorkspaceView 允许某 actor 写入，不会自动把该路径提升为 group shared；只有同时满足 WorkspaceView 与 `shared_write` 才可配置 shared GID。`container-per-group` v1 禁止跨 container 共享 RW volume，中途文本由 Harness memory / prompt 转发，物理 handoff 延后到 [GitHub issue #2](https://github.com/ffy6511/BORA/issues/2)。

`evaluation/`、gold、hidden test 与 evaluator-only material 永远不能成为 handoff source，也不得通过 `shared_write`、workspace 交集或 publish side channel 暴露给 Harness/Agent。`publish_*` 只接收已声明的终局 output，并在 writer barrier 后按 `evaluation.inputs` allowlist materialize。

### 10.4. Prompt 隔离与物理隔离（可见性投影）

本节落实 §0.4：多 Agent / Harness / Evaluator 的**控制可见性**由明确的 projection 机制完成，属于 Core 必保能力。

| 隔离类型 | Owner | 投影机制 | 例子 |
| --- | --- | --- | --- |
| 消息和 prompt 可见性 | Harness Context / upstream memory | 文本过滤 / 分收件人 message | Reviewer 不接收 Writer 私有 reasoning |
| 文件可见性 | Provider | workspace **path view**、mount、PathGrant、L2 UID/GID | Agent 只读 `/task/prompts`；Harness 不挂 `evaluation/` |
| 网络可见性 | Provider | network **projection** | Agent 不能直连 database admin endpoint |
| Secret 可见性 | Runtime | credential **projection** | 只有受控 Adapter 获得 token |
| 产物可见性 | Artifact capability | publish + **materialize** 只读副本 | Reviewer inbox、evaluator inputs |
| 参数可见性 | Config lock + `ctx.params` | parameter **view** | Harness 只见 `parameters`，不见 gold 文件内容 |
| Evaluator 可见性 | Provider mount + evaluator runtime | 评测前单独 materialize allowlist | hidden gold 不进入 Agent 或 Harness workspace |

Context filtering 不能替代物理隔离。`evaluation/` 即使位于 Task Package 中，也由 Runtime 从 package store 在 writer stop 后单独 materialize，不能因为 Harness 需要读取部分 `/task` 路径就把 gold 一并挂载。多个 Agent 挂载同一个可写 volume 时，它们拥有相同 filesystem visibility，除非 Provider 建立不同 path view、mount 或 OS permission。
