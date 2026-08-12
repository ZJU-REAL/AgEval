# 03 — Harness 层：职责与结构

| 字段 | 值                                                                                 |
| ---- | ---------------------------------------------------------------------------------- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA）                                   |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档）  |
| 摘要 | Harness 与 Harness Core 边界、骨架、Agent/Context/Tool/Workflow、参数与 upstream。 |

---

## Harness 里面是什么

### Harness 的职责

Harness 是一个普通 Python 程序，拥有一次 Attempt 内的业务算法：

- 创建 Agent 或复用 upstream Agent object；
- 维护 messages、Context、team memory 和 provider session；
- 定义本地 Tool，并把外部 Tool 包装到 Environment capability；
- 执行 loop、router、branch、fan-out、join、retry 和 stop condition；
- 解释 `bora.yaml` 中的实验参数；
- publish `bora.yaml` 已声明的 output；
- 返回 `HarnessTerminal`，由 publish registry 记录本次输出。

Harness 不创建 Run/Trial/Attempt，不读取 Provider credential，不取得 Docker socket，不启动 hidden evaluator，也不发布最终 score。

### Harness 与 Harness Core 的区别

`harness.py` 是 task 的真实工作流。Harness Core 是可选的通用 Python 积木：

| Harness 内部组成 | Harness Core 提供什么                                      | Task/Framework 决定什么                                      |
| ---------------- | ---------------------------------------------------------- | ------------------------------------------------------------ |
| Agent loop       | `Agent`、`AgentSession`、`AgentResult`                     | prompt、角色、轮数、何时调用                                 |
| Context          | `Message`、`Context`、`ContextTransform`                   | 谁看哪些消息、如何 summary、是否用 upstream memory           |
| Tool             | `Tool`、`ToolSet`、`Observation`                           | Tool 业务函数、schema、说明和调用时机                        |
| Hook             | `before_tool_call`、`after_tool_call`、`should_stop`       | hook 顺序和 task-local policy                                |
| Guard            | `CallLimit`、`AllowList`、`RetryPolicy`、`NoProgressGuard` | 参数值和拒绝后的业务处理                                     |
| Workflow         | `bounded_gather`、`first_success`、`collect_results`       | branch、join、reducer 和失败策略                             |
| Runtime view     | `RunScope`、`HarnessTerminal`                              | 何时提前停止、返回什么 task-local reason                     |
| Artifact helper  | `publish_json`、`publish_file`                             | 哪个 declared output 已提交；materialize 由 Runtime 内部处理 |

Harness Core 没有全局 Registry，也不要求所有 Benchmark 使用这些 helper。上游 Framework 已经拥有相同能力时，直接复用 upstream。

### Harness 的基本骨架

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = TaskParams.from_view(ctx.params)
    environment = ctx.environment.require(params.environment_id)

    tools = ToolSet(
        tools=build_tools(environment),
        hooks=[
            AllowList(params.allowed_tools),
            CallLimit(per_tool=params.tool_limits),
        ],
    )

    agent = Agent(
        actor="solver",
        model_profile=params.model_profile,
        max_turns=params.max_turns,
        invoke=ctx.agent.invoke,
    )

    result = await run_task_loop(
        agent=agent,
        tools=tools,
        scope=ctx.scope,
    )

    await ctx.artifacts.publish_json(
        logical_name="final-output",
        value=result,
    )
    return HarnessTerminal.completed()
```

这里的 `CallLimit`、`Context` 和 loop 都在 Harness 进程内。真实 Agent invocation、外部 Environment action 和跨 workspace Artifact 才进入 Runtime Capability。

### Agent

`Agent` 负责一次或多次模型调用的通用样板：

- messages 和 system instruction；
- structured output schema；
- 调用 `ctx.agent.invoke`；
- provider session continuation；
- usage observation；
- turn loop 和 terminal reason。

角色只是 Harness 的 label。Runtime 不内置 Planner、Reviewer、Executor 或 specialist 类型。

### Context 与 memory

`Context` 只处理 Agent 输入：append、select、transform、render 和 compaction。它可以按 recipient 构造不同 prompt，也可以完全交给 upstream Framework。

```python
planner_context = team_context.for_recipient("planner")
worker_context = team_context.for_recipient(
    "worker",
    task=assignment,
)
```

文本可见性和物理可见性分开：Context 决定模型收到什么文字；Provider 的 mount、UID/GID、network 和 secret projection 决定进程实际能访问什么。

### Tool、Hook 与 Guard

本地 Tool 是普通 callable：

```python
parse = Tool(
    name="parse",
    call=parse_document,
)
```

外部 Tool 在 callable 内调用 Capability：

```python
database = ctx.environment.require("database-attempt")

inspect_locks = Tool(
    name="inspect_lock_contention",
    call=lambda: database.action(
        "inspect_lock_contention",
        {},
    ),
)
```

Tool 的次数、allowlist、retry 和 confirmation 都可以用 stateful hook 处理。参数值来自 `ctx.params`，检查发生在 Harness 内存中。

### Workflow

Harness 用 Python 表达动态控制流：

```python
initial = await bounded_gather(
    (specialist.run(item) for item in assignments),
    limit=params.specialist_concurrency,
)

decision = await planner.run(planner_messages(initial))

if decision.follow_up is not None:
    follow_up = await specialists[
        decision.follow_up.actor_id
    ].run(decision.follow_up.question)
    initial.append(follow_up)

result = await reducer.run(reducer_messages(initial))
```

Runtime 不需要预先知道会不会出现 follow-up，也不生成 branch plan 或 join authority。

### 数据交接

Harness 内按最轻的方式传递数据：

1. 同一函数调用：Python value；
2. 同一 Harness 进程：dataclass、Pydantic model 或 JSON-compatible object；
3. 多角色 loop：Harness / upstream memory 保存结果并序列化进下一轮 prompt，Core 不感知；
4. `shared-container` 同 group 文件协作：只使用 lock 中显式授权的 `shared_write` 相对路径；
5. Harness 到 Evaluator：使用 `publish_*` 提交终局 declared output，Harness 停止后由 Runtime 固定并 materialize allowlisted input。

`container-per-group` v1 不挂跨容器共享可写 volume。跨容器中途物理交接延后到 [GitHub issue #2](https://github.com/ZJU-REAL/BORA/issues/2) 的独立 `handoff_*` 设计；它与终局 `publish_*`、Evaluator input 和 PASS authority 分离。

### 参数进入 Harness

Harness 不读取 YAML：

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = Database52Params.from_view(ctx.params)
```

完整链路是：

```text
bora.yaml
  → Config Core
  → LockedTaskConfig.parameters
  → HarnessParameterView
  → typed TaskParams
  → Agent、Tool、Guard 和 workflow
```

### Upstream Framework

AgentVerse、LangGraph 或其他 Framework 已经拥有 Agent object、memory、router 和 loop 时，Task Package 只需要注入边界 callback。自动或半自动转换应优先识别这些现成入口，避免先把 upstream workflow 翻译成 BORA DTO：

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = AgentVerseParams.from_view(ctx.params)
    team = build_upstream_team(
        llm=agentverse_llm_callback(
            ctx.agent,
            params.model_profile,
        ),
        environment=environment_wrapper(ctx.environment),
    )
    result = await team.run(params.task_input)
    return map_terminal(result, ctx.artifacts)
```

BORA 不复制 upstream team memory，也不要求 upstream message 转换成平台 Conversation DTO。
