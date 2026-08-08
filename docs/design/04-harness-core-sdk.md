# 04 — Harness Core（SDK）详细设计

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | entrypoint、HarnessContext、参数解析、AgentSession、Tool/Guard、workflow helpers。 |

---

## Harness Core 详细设计

### Harness entrypoint

Runtime 根据 `LockedTaskConfig.harness` 启动 package-local runtime，并调用统一入口：

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    ...
```

Harness 不接收配置文件路径，也不执行 `yaml.safe_load`。所有参数通过 `ctx.params` 获得。

### HarnessContext

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessContext:
    params: "HarnessParameterView"
    scope: "RunScope"
    agent: "AgentCapability"
    environment: "EnvironmentCapability"
    workspace: "WorkspaceCapability"
    artifacts: "ArtifactCapability"
    events: "EventSink"
```

`HarnessContext` 是 Harness 获取本次 Attempt 外部能力的唯一入口：

- `params`：`LockedTaskConfig.parameters` 的不可变只读 **parameter projection**（`HarnessParameterView`）；
- `scope`：Attempt identity、deadline、cancel signal 和 remaining time；
- `agent`：真实 Agent Provider invocation（绑定已投影的 profile / workspace view）；
- `environment`：已声明外部 resource 的 scoped client；
- `workspace`：当前 actor 或 invocation 的路径 **view**（物理可见性投影的客户端面）；
- `artifacts`：publish 已在 `artifacts.publishable` 声明的 output；materialize 视图由 Runtime 控制；
- `events`：少量通用运行事件。

这些对象绑定当前 Attempt。Harness 结束后进入 closed 状态，后续调用返回明确错误。

#### L1 多 Actor Session 与 loop 内上下文

L1 下 `Agent.session` 必须显式传 `actor_id`：

```python
async with ctx.agent.session(
    params.planner_model,
    actor_id="planner",
    max_turns=params.planner_max_turns,
) as session:
    decision = await session.invoke(planner_context.render())
```

Session 创建时一次性绑定 Attempt、`actor_id`、profile、WorkspaceView 与 Runtime target generation；同一 session 不允许切换 actor/profile，Harness 只能持有 opaque `session_id`。L0 可以保留不带物理隔离语义的兼容 actor label，L1 缺少 `actor_id` 必须在 open 阶段拒绝。

多角色 loop 的中间结果默认保存在 Harness 或 upstream Framework memory 中，由 Harness 序列化进下一轮 prompt，Core 与 SDK 不建立 team memory 或 mailbox。`publish_json` / `publish_file` 仅提交终局 declared artifact，供 evaluator / Result 边界使用；它们不承担 loop 中途跨 actor 交接。跨容器 immutable physical handoff 是独立的未来 capability，跟踪于 [GitHub issue #2](https://github.com/ffy6511/BORA/issues/2)。同容器文件协作只能使用 lock 中显式授权的 `shared_write`。

### 参数解析

每个 Harness 在入口处把 `ParameterView` 转成自己的 typed params。解析只发生一次：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Database52Params:
    specialist_model: str
    planner_model: str
    reducer_model: str
    specialist_concurrency: int
    max_follow_up_assignments: int
    specialist_max_turns: int
    planner_max_turns: int
    reducer_max_turns: int
    tool_limits: dict[str, int]

    @classmethod
    def from_view(
        cls,
        view: HarnessParameterView,
    ) -> "Database52Params":
        default_max_calls = view.require_int(
            "tools.defaults.max_calls"
        )
        return cls(
            specialist_model=view.require_str("models.specialist"),
            planner_model=view.require_str("models.planner"),
            reducer_model=view.require_str("models.reducer"),
            specialist_concurrency=view.require_int(
                "workflow.specialist_concurrency"
            ),
            max_follow_up_assignments=view.require_int(
                "workflow.max_follow_up_assignments"
            ),
            specialist_max_turns=view.require_int(
                "agents.specialist.max_turns"
            ),
            planner_max_turns=view.require_int(
                "agents.planner.max_turns"
            ),
            reducer_max_turns=view.require_int(
                "agents.reducer.max_turns"
            ),
            tool_limits={
                action_id: default_max_calls
                for _, _, action_id in BRANCHES
            },
        )
```

参数值只存在于 `bora.yaml` 和 resolved lock。`Database52Params` 定义类型和读取位置，不维护第二份默认值。

### Harness Core 的范围

Harness Core 是可选 Python library。它减少重复样板，不创建 Run、Trial 或 Attempt，也不发布最终 verdict。

| 模块 | 主要对象 | 职责 |
| --- | --- | --- |
| Agent | `Agent`、`AgentSession`、`AgentResult` | 调用 Agent capability、处理 structured output 和 session continuation |
| Context | `Message`、`Context`、`ContextTransform` | append、select、transform、render、compaction |
| Tool | `Tool`、`ToolSet`、`Observation` | callable 注册、参数校验、hook chain、结果转换 |
| Hook | `before_turn`、`before_tool_call`、`after_tool_call`、`should_stop` | 局部扩展点 |
| Guard | `CallLimit`、`AllowList`、`RetryPolicy`、`NoProgressGuard` | Harness 内可拦截策略 |
| Workflow | `bounded_gather`、`first_success`、`collect_results` | 普通异步组合 helper |
| Scope | `RunScope`、`HarnessTerminal` | deadline、cancel、终态 |
| Artifact helper | `publish_json`、`publish_file` | 向 Runtime publish registry 提交 declared output |
| Event | `EventSink` | Agent、Tool 和 Harness terminal 的通用事件 |

上游 Framework 已经提供其中某项能力时，Task Package 可以绕过对应 helper。

### Agent 与 AgentSession

`Agent` 封装一次或多次模型调用所需的通用操作：

- 接收 messages、system instruction 和 output schema；
- 调用 `ctx.agent.invoke`；
- 返回 normalized content、typed output、usage observation 和 session handle；
- 可选维护 provider continuation；
- 将 turn 事件写入 Harness event sink。

创建 `AgentSession` 时一次性绑定 Attempt、model profile 和 WorkspaceView，并校验它们来自同一份 locked config。绑定后的 invoke 热路径只需检查 capability 是否仍打开、cancel/deadline、Attempt 级调用计数和 Provider 调用结果；profile/workspace 不在每次调用时重新解析。跨 Attempt 复用 session 直接失败。

```python
agent = Agent(
    invoke=ctx.agent.invoke,
    actor="planner",
    model_profile=params.planner_model,
    max_turns=params.planner_max_turns,
)

decision = await agent.run(
    messages=planner_context.render(),
    output_schema=PlannerDecision,
    scope=ctx.scope,
)
```

角色由 Harness 创建。Runtime 只把 `actor` 当作日志 label，不从角色名推导权限；WorkspaceView 由 locked `agent_profiles.workspace_view` 在 session 创建时绑定。

### Message 与 Context

`Context` 管理 Agent 输入：

```python
context = Context([user_message])
context = context.append(tool_observation)

planner_view = context.for_recipient("planner")
planner_view = planner_view.transform(
    strategy=params.context_strategy
)
```

它可以提供：

- sender、recipient、channel 和 message kind；
- append、select、map 和 render；
- recent-window、summary 或 task-local compaction；
- attachment reference；
- 按 Agent 构造不同 prompt projection。

Context 只决定模型看到什么文本和引用。文件、网络、secret、UID/GID 和 evaluator material 由 Runtime 的物理 capability 决定。

AgentVerse 等 Framework 已经拥有 team memory、receiver routing 和 speaker selection 时，BORA 直接使用 upstream object，不复制第二份 Context。

### Tool、Hook 与 Guard

`Tool` 是普通 callable 加上可选 metadata：

```python
tool = Tool(
    name="inspect_lock_contention",
    description="读取当前锁等待情况",
    input_schema=EmptyArguments,
    call=inspect_lock_contention,
)
```

`ToolSet` 负责：

- 根据 Agent action 找到 callable；
- 校验参数；
- 顺序执行 hooks；
- 调用 Tool；
- 将返回值转成 Observation；
- 写入 Harness event sink。

Hook chain 由 Harness 显式构造：

```python
tools = ToolSet(
    tools=diagnostic_tools,
    hooks=[
        AllowList(allowed_tool_ids),
        CallLimit(per_tool=params.tool_limits),
        RetryPolicy(max_attempts=params.tool_retry_attempts),
    ],
)
```

这些对象保存在 Harness 进程内。每次调用只检查内存状态，不需要向宿主 Tool Service 请求许可。

### Tool 上限的配置与执行

Tool 上限的声明链路固定为：

```text
bora.yaml parameters.tools.defaults.max_calls / overrides
  → Config Core
  → LockedTaskConfig.parameters
  → HarnessParameterView
  → typed Params
  → CallLimit
  → 进程内调用前检查
```

例如：

```yaml
parameters:
  tools:
    defaults:
      max_calls: 2
```

```python
limit = CallLimit(
    per_tool={
        "inspect_lock_contention": 2,
    }
)
```

外部资源还可以有 Runtime 硬上限：

```yaml
limits:
  environment_actions: 20
```

两个上限处理不同范围：

| 上限 | 执行者 | 含义 |
| --- | --- | --- |
| `parameters.tools.inspect_lock_contention.max_calls: 2` | Harness `CallLimit` | 业务 Tool 在当前 loop 中最多调用两次 |
| `limits.environment_actions: 20` | Runtime Environment capability | 整个 Attempt 最多产生二十次外部 Environment action |

它们来自同一个配置文件，不需要共用同一种执行机制。

### Workflow helpers

Python 已经提供循环、条件、异常、generator 和 `asyncio`。Harness Core 只补少量无 authority 的 helper：

```python
results = await bounded_gather(
    (worker.run(item) for item in work),
    limit=params.specialist_concurrency,
)

winner = await first_success(candidates)

valid = collect_results(results, predicate=lambda item: item.ok)
```

这些函数不创建 Trial、后台 worker 或 durable scheduler。Campaign concurrency、Provider capacity 和 Harness 内 fan-out 属于不同层级。

### Upstream bridge

转换已有 Framework 时，优先使用 callback bridge：

```python
def agentverse_llm_callback(
    ctx: HarnessContext,
    model_profile: str,
):
    async def invoke(
        messages: list[dict[str, str]],
    ) -> dict[str, object]:
        response = await ctx.agent.invoke(
            AgentRequest(
                model_profile=model_profile,
                messages=tuple(messages),
            )
        )
        return {
            "content": response.content,
            "usage": response.usage,
            "session": response.session,
        }

    return invoke
```

upstream 继续维护 Agent object、team memory、speaker selection 和内部 Tool loop。Bridge 只转换函数签名，不保存第二份 workflow state。
