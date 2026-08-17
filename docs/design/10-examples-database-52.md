# 10 — 示例：database-52 对比与 MVP 主路径

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 归档 v1 v0.9 与 v2 的配置/Harness/Runtime 对照，以及 database-52-mvp 概念主路径。 |

---

## `database-52`：v0.9 与 v2 MVP 的代码对比

本节以文档内的 `database-52-mvp/` 为 v2 主示意，比较同一个 MARBLE task 从归档 v1 的 v0.9 workflow-aware Runtime 转向薄公共契约后的差异。`database-52/` 是展开 multi-service、细粒度 workspace 和完整术语的概念对照；本文完整复现所需配置与代码片段，不要求 v2 greenfield 仓库存在这些目录。

### v0.9 的配置同时描述 Runtime 和 workflow

归档 v1 v0.9 的 `benchmarks/multiagentbench/tasks/database-52/bora.yaml` 包含：

```yaml
actors:
  - actor_id: insert-specialist
    role: specialist
    capability_ids: [inspect_insert_workload]
  - actor_id: planner
    role: planner
  - actor_id: reducer
    role: reducer

tools:
  - tool_id: inspect_insert_workload
    actor_ids: [insert-specialist]
    binding:
      type: environment_action
      environment_id: database-attempt
      action_id: inspect_insert_workload
    max_invocations: 2

branch_plans:
  - branch_id: insert-workload
    actor_id: insert-specialist
    hypothesis: INSERT_LARGE_DATA
    allowed_tool_ids: [inspect_insert_workload]

branch_execution:
  mode: foreground_serial
  branch_order:
    - insert-workload
    - lock-contention
    - vacuum-health
    - redundant-index
    - fetch-workload

collaboration:
  planner_actor_id: planner
  reducer_actor_id: reducer
  max_follow_up_assignments: 1
  required_label_count: 3
```

这些字段进入 `TaskLockedV1`，Runtime 因而需要理解 Actor、Tool、branch、Planner、follow-up、join 和 Reducer。

### 新配置只声明参数和外部 envelope

目标 `bora.yaml` 把模型、轮数、Tool 次数和 workflow 上限集中到 `parameters`，把 Provider、Environment、Artifact 和 Evaluation 继续作为外部 contract：

```yaml
format: bora.task/1
task_id: database-52

harness:
  runtime: python
  entrypoint: harness:run

parameters:
  models:
    specialist: codex-database-specialist
    planner: codex-database-planner
    reducer: codex-database-reducer
  workflow:
    specialist_concurrency: 5
    max_follow_up_assignments: 1
  agents:
    specialist: { max_turns: 1 }
    planner: { max_turns: 1 }
    reducer: { max_turns: 1 }
  tools:
    defaults:
      max_calls: 2

provider:
  kind: docker
  platform: linux/arm64
  assurance: l1
  workspace:
    views:
      harness:
        read: [/task/harness.py, /task/lib, /task/prompts, /task/schemas]
        write: [/workspace]
      agents:
        read: [/task/prompts, /task/schemas]
        write: [/workspace/work]

agent_profiles:
  - id: codex-database-specialist
    workspace_view: agents
  - id: codex-database-planner
    workspace_view: agents
  - id: codex-database-reducer
    workspace_view: agents

environment:
  id: database-attempt
  kind: multi-service
  # multi-service 表示 component 组合能力；MVP 可以只含一个 PostgreSQL component
  action_commands:
    - command_id: postgres-readonly-diagnostic
      action_ids:
        - inspect_insert_workload
        - inspect_lock_contention
        - inspect_vacuum
        - inspect_redundant_indexes
        - inspect_fetch_workload

limits:
  wall_time_seconds: 900
  agent_invocations: 8
  environment_actions: 20

artifacts:
  publishable:
    - id: reducer-output
      path: artifacts/reducer-output.json

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: reducer-output
      target: artifacts/reducer-output.json
    - package_path: evaluation/task.json
      target: task.json
```

`multi-service` 表示 Environment Adapter 可以组合多个 component，不要求 sidecar 齐套；MVP 只声明当前 task 实际消费的 PostgreSQL。配置仍统一管理所有超参数，但 Runtime 不解释 `max_follow_up_assignments` 或每个 Tool 的 `max_calls`。它们通过 `ctx.params` 交给 Harness。

### v0.9 Harness 需要对接 Runtime workflow authority

归档 v1 v0.9 的 `harness.py` 通过多个 BORA effect wrapper 和 callback 组织同一个 loop：

```python
from bora_sdk import (
    authorize_branch_with_receipt,
    invoke_tool_with_receipt,
    invoke_with_receipt,
    open_join_with_receipt,
    publish_with_receipt,
    resolve_with_receipt,
    validate_planner_with_receipt,
    validate_reducer_with_receipt,
)

reducer_output = run_collaboration(
    initial_handoffs=initial_handoffs,
    planner_actor_id="planner",
    reducer_actor_id="reducer",
    resolve=resolve,
    invoke_planner=invoke_planner,
    validate_planner=validate_planner,
    authorize_follow_up=authorize_follow_up,
    invoke_follow_up=invoke_follow_up,
    open_join=open_join,
    invoke_reducer=invoke_reducer,
    validate_reducer=validate_reducer,
)
```

Harness 已经有真实 Python control flow，但 Planner validation、Branch admission、Handoff publish/resolve、Join 和 Reducer validation 仍由 Runtime authority 表达。

### 新 Harness 直接拥有 workflow

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = Database52Params.from_view(ctx.params)
    environment = ctx.environment.require("database-attempt")

    diagnostics = ToolSet(
        tools=build_diagnostic_tools(environment),
        hooks=[CallLimit(per_tool=params.tool_limits)],
    )

    specialists = build_specialists(
        invoke=ctx.agent.invoke,
        model_profile=params.specialist_model,
    )

    initial = await run_initial_investigations(
        specialists=specialists,
        diagnostics=diagnostics,
        concurrency=params.specialist_concurrency,
    )

    planner = Agent(
        actor="planner",
        model_profile=params.planner_model,
        invoke=ctx.agent.invoke,
    )
    decision = await planner.run(
        messages=planner_messages(initial),
        output_schema=PlannerDecision,
    )

    follow_ups = await run_follow_ups(
        decision=decision.output,
        maximum=params.max_follow_up_assignments,
        specialists=specialists,
        diagnostics=diagnostics,
    )

    reducer = Agent(
        actor="reducer",
        model_profile=params.reducer_model,
        invoke=ctx.agent.invoke,
    )
    reduced = await reducer.run(
        messages=reducer_messages([*initial, *follow_ups]),
        output_schema=ReducerOutput,
    )

    await ctx.artifacts.publish_json(
        logical_name="reducer-output",
        value=reduced.output,
    )
    return HarnessTerminal.completed()
```

五个 specialist、Planner、output-dependent follow-up 和 Reducer 都是普通 Python 结构。每次真实 Agent 调用仍通过 `ctx.agent`，每次数据库诊断仍通过 `ctx.environment`。

### 一次 Tool 调用的变化

v0.9 先在 YAML 声明业务 Tool 和 Actor binding，再从 Harness 请求 Runtime dispatcher：

```python
result = invoke_tool_with_receipt(
    actor_id,
    tool_id,
    {},
    environment_id="database-attempt",
    idempotency_key=(
        f"database-52-{branch_id}-diagnostic"
    ),
    state={},
)
```

新设计在 Harness 内组合 Tool，调用次数由进程内 `CallLimit` 管理：

```python
database = ctx.environment.require("database-attempt")

diagnostics = ToolSet(
    tools=[
        Tool(
            name="inspect_insert_workload",
            call=lambda: database.action(
                "inspect_insert_workload",
                {},
            ),
        )
    ],
    hooks=[
        CallLimit(
            per_tool={
                "inspect_insert_workload": (
                    params.tool_limits[
                        "inspect_insert_workload"
                    ]
                )
            }
        )
    ],
)
```

`max_calls` 仍在 `bora.yaml` 中统一声明。Harness 的内存 guard 执行业务 Tool 上限；Runtime 的 Environment capability 执行外部 action allowlist、总 action ceiling 和 teardown，只在 stateful evaluator 声明对应 input strategy 时执行 freeze/getter。

### Runtime Core 的变化

归档 v1 v0.9 的 Docker Harness path 会直接从 locked document 读取 workflow 字段，并建立 workflow-aware authority。下面的代码片段作为历史结构对照完整保存在本文；v2 greenfield 仓库当前没有对应源码路径：

```python
tools = locked_tools(lock.document.get("tools", []))
branch_plans = locked_branch_plans(
    lock.document.get("branch_plans", [])
)
collaboration = locked_collaboration(
    lock.document.get("collaboration")
)
handoff_store = HandoffStore(attempt_id=context.run_id)

if collaboration is not None:
    planner_contract = PlannerContract(
        plans=branch_plans,
        eligible_actor_ids=tuple(
            collaboration["eligible_actor_ids"]
        ),
        max_follow_up_assignments=collaboration[
            "max_follow_up_assignments"
        ],
    )
    branch_authority = BranchAuthority(
        plans=branch_plans,
        deadline=time.monotonic() + self._timeout_seconds,
    )
    reducer_contract = ReducerContract(
        allowed_labels=tuple(collaboration["allowed_labels"]),
        required_count=collaboration["required_label_count"],
    )

authority = EffectAuthority(
    allowed_tools=tools,
    allowed_branch_plans=branch_plans,
    collaboration_enabled=collaboration is not None,
    max_follow_up_assignments=(
        collaboration["max_follow_up_assignments"]
        if collaboration is not None
        else 0
    ),
    # 其他 Attempt、deadline 和外层 budget 参数省略
)
```

新 Core 只锁定和实例化外部边界：

```python
locked = config_core.load_and_lock(
    package_root=package_root,
    task_id="database-52",
    variant=variant,
    overrides=overrides,
)

ctx = HarnessContext(
    params=locked.parameter_view(),
    scope=attempt_scope,
    agent=agent_capability,
    environment=environment_capability,
    workspace=workspace_capability,
    artifacts=artifact_capability,
    events=event_sink,
)
```

### 对比结论

| 维度 | v0.9 | 新 Core |
| --- | --- | --- |
| 配置 | Runtime envelope 与 workflow 声明混合 | Database 根 `bora.yaml` + 成员 `task.yaml`；超参数集中，workflow 结构留在代码 |
| Config | 生成包含 Actor、Tool、Branch、Collaboration 的 `TaskLockedV1` | `load_and_lock()` 生成一份外部运行边界和参数锁定对象 |
| Harness | 调用多个 Runtime workflow authority | 直接拥有 loop、branch、join 和 reducer |
| Context | 平台 DTO 与 task code 并存 | Harness/upstream memory 拥有 |
| Tool | YAML declaration + dispatcher + authority | Harness `ToolSet` + hooks；外部 action 调用 Capability |
| Adapter | 可能参与 Tool/Service/workflow binding | 只实现 Provider、资源或协议 |
| Evaluator | writer barrier 后独立评测 | 保持不变 |
| 物理隔离 | Provider、workspace、network、secret | 保持并明确为 Core 机制 |

## `database-52-mvp` 主路径

`database-52-mvp/` 是本设计中的默认概念示意：单 PostgreSQL、L1 path views、`max_turns: 1`、publish registry 和 artifact-only evaluator。它保留同一 `task_id: database-52`，因此可以与归档 v1 v0.9 和 `database-52/` 概念对照比较 workflow 语义，而不会把 package 形态误当成新任务。

### 业务结构留在代码中

```python
BRANCHES = (
    (
        "insert-specialist",
        "INSERT_LARGE_DATA",
        "inspect_insert_workload",
    ),
    (
        "lock-specialist",
        "LOCK_CONTENTION",
        "inspect_lock_contention",
    ),
    (
        "vacuum-specialist",
        "VACUUM",
        "inspect_vacuum",
    ),
    (
        "index-specialist",
        "REDUNDANT_INDEX",
        "inspect_redundant_indexes",
    ),
    (
        "fetch-specialist",
        "FETCH_LARGE_DATA",
        "inspect_fetch_workload",
    ),
)
```

这组值描述当前 task 的业务结构，因此留在 `harness.py`。如果 branch 集合成为 experiment variable，再把它提升到 `parameters`。

### Tool 绑定

```python
def build_diagnostic_tools(
    environment: EnvironmentClient,
) -> list[Tool]:
    return [
        Tool(
            name=action_id,
            call=lambda action_id=action_id: environment.action(
                action_id,
                {},
            ),
        )
        for _, _, action_id in BRANCHES
    ]
```

Environment action 经过 Runtime capability。Tool 的名称、说明、业务参数和组合方式仍由 Harness 拥有。

### MVP 入口

下面的完整设计示意限定 ownership 与调用链；具体 helper 签名由后续实现 / SDK 契约在不改变这些边界的前提下冻结：

```python
async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = Params.from_params(ctx.params)
    environment = ctx.environment.require("database-attempt")

    diagnostics = ToolSet(
        tools=build_tools(environment),
        hooks=[CallLimit(per_tool=params.tool_limits)],
    )

    specialists = build_specialists(params, ctx.agent.invoke)
    findings = await run_initial_findings(
        specialists=specialists,
        diagnostics=diagnostics,
        limit=params.specialist_concurrency,
    )
    decision = await run_planner(params, findings, ctx.agent.invoke)
    follow_ups = await run_follow_ups(
        decision=decision,
        maximum=params.max_follow_up_assignments,
        specialists=specialists,
        diagnostics=diagnostics,
        previous=findings,
    )
    reduced = await run_reducer(
        params,
        [*findings, *follow_ups],
        ctx.agent.invoke,
    )

    await ctx.artifacts.publish_json(
        logical_name="reducer-output",
        value=reduced.output,
    )
    return HarnessTerminal.completed()
```

这段中性伪代码直接表达五个 specialist、Planner、output-dependent follow-up 和 Reducer，不把 `scope` 参数或具体 helper 签名提升为公共要求。Runtime 只看到真实 Agent invocation、Environment action、Artifact publish 和 Harness terminal。

### 当前静态 authority 的去向

| v0.9 结构 | v2 owner |
| --- | --- |
| `actors` | Harness 创建 `Agent` 或 upstream Agent object |
| `tools` | Harness `ToolSet` |
| `branch_plans` | `BRANCHES` 和普通 Python data |
| `branch_execution` | `bounded_gather`、循环或 upstream scheduler |
| `collaboration` | Planner/follow-up/Reducer 代码和 `parameters.workflow` |
| `HandoffStore` | 普通 Python object、message 或 upstream memory |
| `BranchAuthority` | Harness condition + `max_follow_up_assignments` |
| `ReducerContract` | Harness output schema + 独立 evaluator |
| `DeclaredToolDispatcher` | Harness `ToolSet`；外部 action 进入 Environment capability |

Provider、Environment lifecycle、Agent invocation hard ceiling、declared output 固定和 Evaluator barrier 继续由 Runtime 持有。

### 完整 envelope 对照

文档内的 `database-52/` 概念对照增加 postgres-exporter、Prometheus、node-exporter、细粒度 actor workspace 与更完整的内部术语，用于说明复杂资源组合怎样落在同一外层边界中。它不定义 MVP 必需能力，也不应反向要求简单 task 配置未消费的 service、per-actor UID/GID、freeze 或 Artifact 类型阶梯。

| 场景 | 主示意 `database-52-mvp/` | 完整对照 `database-52/` |
| --- | --- | --- |
| Environment | 单 PostgreSQL | multi-service metrics stack |
| 隔离 | L1，Harness/Agent 两个 path view | 更细 actor view，可继续提升档位 |
| Tool 软限 | `tools.defaults.max_calls` | 可逐 Tool 展开 |
| Evaluation | declared JSON + hidden gold | 可展示更多 input strategy |
