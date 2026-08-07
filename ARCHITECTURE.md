# BORA Architecture

本文只维护**实现结构**：当前 vs 目标布局、模块所有权、依赖方向、composition root、运行生命周期、跨边界数据流、失败/清理归属、证据分类与变更同步。  

- **不**写产品长文、版本勾选清单、Phase 任务表。  
- 产品与机制设计权威：[docs/](docs/README.md)（尤其 [docs/design/](docs/design/)）。  
- 版本交付与验收：[specs/ROADMAP.md](specs/ROADMAP.md)。  
- 实现增量与证据：[specs/active/](specs/active/)。

## Document Status

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 代际 | v2 greenfield |
| 实现状态 | **v0.1–v0.13 L0 竖切 + Attempt evidence** — `bora lock`/`run`/`campaign`；§8.9 trajectory store（Codex path）；Docker L1 multi-actor SDK scheduling（`agent_isolation` shared-container / container-per-group）+ multi-executor / env 部分切片 |
| 证据等级 | **限定 `runnable-mvp`**（L0 core/journeys 烟测；见 `examples/README.md`；Version Index 以 Roadmap 为准） |
| 设计权威 | [docs/README.md](docs/README.md) |
| 结构权威 | **本文**（模块/依赖/生命周期地图） |
| 近端目标结构依据 | [docs/design/01](docs/design/01-bora-core.md)、[docs/design/09](docs/design/09-owner-matrix-and-structure.md)、[ROADMAP v0.1–v0.6](specs/ROADMAP.md) |
| 更新触发 | 见文末 [Change Ownership](#change-ownership) |

**禁止**把下方 Target 树或流程图当作「已实现」。Current 与 Target 必须分开阅读。

## System Overview

BORA 是 **Harness 的 Harness**：外层执行内核准备并锁定运行边界，注入 Capability，启动 package 自带的 Harness（或 upstream bridge），在 writers 停止后独立评测并绑定扁平结果。

### 主要参与者

| 参与者 | 职责 | 不负责 |
| --- | --- | --- |
| 操作者 / CLI | 发起 run/inspect、读 exit code 与摘要 | 业务 workflow、评分算法 |
| Application | use case 编排、**唯一 composition root** | 框架无关领域规则的「第二份」实现 |
| BORA Core 1 Config | `load_and_lock` → `LockedTaskConfig` | 解释 Python workflow |
| BORA Core 2 Lifecycle | Run/Trial/Attempt 身份与外层顺序 | Attempt 内业务 loop |
| BORA Core 3 Provider | 物理隔离、mount/network/secret 投影、进程生命周期 | Benchmark 业务语义 |
| BORA Core 4 Capability | 向 Harness 暴露已授权操作面 | 颁发 final PASS |
| BORA Core 5 Evaluation | barrier、evaluator 运行、Result 绑定、evidence | 统一所有评分算法 |
| Harness Core（SDK） | 可选类型与薄 helper | Run/credential/verdict |
| Task Harness | 业务 loop、本地 Tool、参数使用 | Docker/credential/final PASS |
| Adapters / plugins | Codex Executor、Docker Provider 等具体实现 | 按 Benchmark 名分支 |
| Evaluator（package） | task truth | 启动 Agent、持有 host secret |

### 目标数据/控制主流（validated output 方向）

```text
Database root (bora.yaml / bora.database/1)
  → resolve_task(--task) → tasks/<id>/task.yaml
  → load_and_lock → LockedTaskConfig
  → RunCoordinator 创建 Run/Trial/Attempt + evidence 根
  → Provider.prepare（workspace / network / secret 投影）
  → 注入 HarnessContext（Capability）
  → harness entrypoint
       ↘ agent / environment / workspace / artifacts（仅经 Capability）
  → HarnessTerminal
  → close capabilities + stop writers
  → materialize allowlisted evaluator inputs
  → evaluator → raw → bind flat Result
  → cleanup（失败 → warning，不覆盖已形成 score）
```

箭头含义：**控制流推进**；跨信任边界的数据流见 [Data Flow](#data-flowtarget)。

## Runnable System Path

### Current（已验证）

| 项 | 值 |
| --- | --- |
| Public entrypoint | `bora lock` / `bora run` / `bora tasks` / `bora campaign`（CLI 已暴露；campaign/L1 草图边界见 Spec 07–11） |
| Production composition root | `src/bora/application/composition.py` |
| Smoke journey | `uv run bora lock examples/core --task config-minimal`（exit 0，确定性 JSON 摘要含 `database_id`） |
| Expected failure | `uv run bora lock examples/core --task config-invalid`（exit 2，`unknown_profile`）；缺 `--task` → exit 2 |
| Observable result | 无 secret 的 lock summary + digest；无 Run/Attempt/Agent/Evaluator |
| Lifecycle checkpoint | `uv run pytest tests/acceptance/test_lifecycle_application.py -k success_trace -q` |
| 证据等级 | **限定 `runnable-mvp`**（仅上述 L0 真实 Codex journeys；非 full Spec 闭合 / 非 Version Index） |

文档门禁仍须通过：

```bash
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
```

### Target — 首条产品竖切（Roadmap `v0.6`，依赖 `v0.1`–`v0.5`）

| 项 | 计划值 |
| --- | --- |
| Public entrypoint | `bora run <package> --task <id>`（精确 flags 由 Active Spec 冻结） |
| Composition root | `src/bora/application/` 内 bootstrap（名称以实现为准） |
| 最短路径 | CLI → application → load_and_lock → Attempt(L0 或当时已交付 Provider) → harness → Codex AgentExecutor → evaluator → Result + `.bora/runs/<run-id>/` |
| 证据 | CLI 分离展示 runtime vs evaluation；evidence 目录可定位 |

更早的中间可运行检查点（非完整竖切）由 Roadmap 标明，例如 `v0.1` 的 lock/inspect。

## Source Layout

### Current Source Layout

```text
BORA/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── src/bora/
│   ├── __init__.py
│   ├── cli/                   # Typer：argv、help、exit code（main 挂载 + cmd_*）
│   ├── application/           # use cases + composition root（run_l1_* / run_command_* helpers）
│   ├── config/                # Core 1（load_and_lock + constants/yaml_io/overrides/digest/validate）
│   ├── runtime/               # Core 2：identity、lifecycle、coordinator、task_worker、
│   │                          # parent_agent_service + agent_service_protocol/evidence
│   ├── provider/              # Core 3：L0 contract / workspace plan / outcomes / targets+isolation
│   ├── capabilities/          # Core 4：Attempt authority（进程内）
│   ├── evaluation/            # Core 5：flat Result binder（含 Result.logs locator）
│   ├── evidence/              # Attempt evidence store / redaction / §8.9 layout
│   ├── viewer/                # 本地 Jobs/Trial HTTP API（trials/ 包）
│   └── adapters/
│       ├── package_fs.py
│       ├── provider_local.py  # LocalProcessProvider
│       ├── provider_docker/   # Docker L1 + multi-actor ExecutionTarget
│       ├── acp/               # 唯一 typed ACP client（parent；usage/trajectory/client/executor）
│       ├── acp_entries.json   # Current: static entry pins / descriptors
│       ├── acp_registry.py    # Current: registry + readiness
│       ├── agent_container.py # L1 placement helpers / opaque target id
│       └── agent_openai_http.py
├── sdk/python/bora_sdk/       # Harness Core HC-1/2/3 helpers
├── examples/                  # 见 examples/README.md
│   ├── journeys/              # case-class：env / multiagent / tau2 / terminal
│   ├── core/                  # config / harness / eval / agent / SDK / plugin
│   └── l1/                    # Provider L1 isolation probes
├── tests/
│   ├── acceptance/
│   ├── config/
│   └── test_package_baseline.py
├── docs/                      # 设计权威（00–10）
└── specs/                     # Roadmap / Active Specs / BLOCKED
```


### Target Source Layout（planned — 随 Core 交付出现）

以下树是**接受的方向**，不是当前工作树。模块可在 Active Spec 中微调命名，但 **Core 所有权不得并入 Harness workflow 包**。

```text
BORA/
├── pyproject.toml
├── src/bora/
│   ├── cli/                   # Typer：参数、帮助、输出、exit code
│   ├── application/           # use cases + 唯一 composition root（bootstrap）
│   ├── config/                # Core 1：model、load_and_lock、校验
│   ├── runtime/               # Core 2：identity、coordinator、lifecycle、outcomes
│   ├── provider/              # Core 3：契约与 workspace plan（非 Docker 细节）
│   ├── capabilities/          # Core 4：agent/env/workspace/artifacts/events 契约
│   ├── evaluation/            # Core 5：barrier、bind、result 模型
│   ├── domain/                # 薄共享 value types / 错误类型
│   └── adapters/              # 具体 I/O：package fs、docker、credentials、evidence
│       ├── acp/                # 唯一 ACP client（parent；Spec 19 Current）
│       ├── acp_entries.json   # entry descriptor + exact pins
│       ├── agent_container.py # L1 placement helpers
│       └── agent_openai_http.py
├── sdk/python/bora_sdk/       # Harness Core：HarnessContext 等（可选 import）
├── examples/                  # 仓库拥有的回归 package
├── tests/                     # unit / integration / opt-in e2e
├── docker/attempt/            # L1 基座：install-executors + acp-entries.lock（engine+ACP bake-in）
└── （可选）benchmarks/ website/
```

### 生成物（非源码所有权）

| 路径/模式 | 说明 |
| --- | --- |
| `.bora/` | runs、locks、本地 profile、转换 receipt 等 |
| `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` | 工具链 |
| `dist/`、`*.egg-info/` | 构建产物 |

## Module Ownership（Target）

| 路径 | 唯一责任 | 不负责 |
| --- | --- | --- |
| `cli/` | argv、帮助、人类可读输出、exit code 映射 | 读 package 业务、启 Docker、写 evidence 细节 |
| `application/` | run/inspect/campaign 等 use case；**装配 adapters** | 把业务规则藏在 bootstrap 外的隐式全局单例 |
| `config/` | Database resolve；读成员 `task.yaml`、合并、校验、canonicalize、digest、`LockedTaskConfig` | 执行 harness、评测 |
| `registry/`（client）+ `services/registry/` | PackageRef resolve、publish client、verified cache；独立 Registry HTTP 服务 | 不做 PASS / 不持有 store credential 给 CLI |
| `runtime/` | Run/Trial/Attempt、外层状态机、取消/超时进入 cleanup | Provider 实现细节、评分 |
| `provider/`（契约） | 隔离档、workspace plan、进程/容器生命周期接口 | Benchmark 名分支 |
| `capabilities/` | Capability 面与 Attempt 注入契约 | 具体 Codex/DB 实现 |
| `evaluation/` | barrier 顺序、raw 校验、扁平 Result、与 evidence 衔接 | package 内评分逻辑 |
| `adapters/*` | package fs、Docker、credentials、evidence；**Target** ACP client + entry registry；Current residual private CLI adapters | 解释 Benchmark 业务 action catalog；第二套 vendor stdout scrape |
| `domain/` | 跨模块稳定值对象与错误分类 | I/O、Typer、Docker SDK |
| `bora_sdk` | Harness 侧类型与薄 helper | Control Plane 内部类型、verdict |
| `examples/` | 可信回归 package | 声称支持完整 upstream suite |
| `tests/` | 契约与回归证据 | 成为 production composition root |
| `docs/` | 设计与产品规格 | 版本勾选状态、Phase 清单 |
| `specs/` | Roadmap、Active Spec、Research、可选 constitution、BLOCKED | Runtime authority |

## Dependency Direction

依赖箭头含义：**Python import 允许方向**（编译期/静态依赖）。

```text
cli ──────────────► application
                       │
                       ├─► config / runtime / capabilities / evaluation / domain
                       │
                       └─► adapters ──► domain + 契约模块
                                        （adapters 不反向被 domain import）

bora_sdk ──► 仅最小公开 DTO / 协议形状
             （禁止 import application、adapters 内部、Control Plane 私有模块）
```

### 禁止

- `domain/` 或纯契约模块依赖 Typer、Docker SDK、SQLAlchemy、随意 `subprocess` 副作用。  
- CLI 直接调用 Codex、直接写 evidence 树、直接解析 package 业务。  
- Control Plane import/execute task-local `harness.py` / evaluator **作为 Python 模块**。  
- Harness / SDK 取得 host credential 文件内容、Docker socket 控制面、final-result 发布权。  
- 在 composition root **之外**隐式注册全局 Adapter 单例。  
- Adapter 根据 Benchmark 名称、task id、upstream 品牌选择行为。  
- 测试 helper 被 production 代码 import 作为唯一装配路径。  

第三方 workflow SDK：仅允许 task package 或**明确**的 bridge adapter 依赖；不得反向成为 Core authority。

## Composition Root

| 项 | 规则 |
| --- | --- |
| 唯一生产装配点 | `application` 内 bootstrap（实现后写入具体模块路径） |
| 测试 | 可有测试专用 wiring，但公开 smoke 必须走 production CLI 入口 |
| 插件发现 | entry point / 显式配置在装配时解析；失败 fail-closed |

## Lifecycle（Target）

### 外层状态（Attempt）

```text
created
  → preparing      # Provider + resources
  → running_harness
  → harness_terminal
  → sealing_inputs # stop writers + materialize
  → evaluating
  → binding_result
  → cleaning_up
  → terminal       # succeeded | failed | cancelled | …（精确枚举由实现 Spec 固定）
```

### 顺序不变量

1. 未 `load_and_lock` 成功不得启动 harness。  
2. Evaluator 不得与可写 Agent/Harness writer 并发写同一评测输入。  
3. `cleanup` 必须可从超时/取消/异常进入；cleanup 失败 → warning，不覆盖已 bind 的 score。  
4. retry / 重跑 → **新 Attempt**，不静默改写旧 Attempt identity。  
5. Campaign（后期）只调度 Trial，不与 Attempt 内 workflow scheduler 合并。  

详细状态机见 [docs/design/05-runtime-core.md](docs/design/05-runtime-core.md)。

## Data Flow（Target）

| 数据 | 生产者 | 消费者 | 边界规则 |
| --- | --- | --- | --- |
| Database `bora.yaml` + 成员 `task.yaml` / overrides | 作者 / CLI | Config Core | 唯一规范读取 |
| `LockedTaskConfig` | Config | Lifecycle、Provider、Capability、Evaluation | 可复盘；无 secret 明文 |
| `ctx.params` | Config 投影 | Harness | 只读；无 gold/credential |
| Agent prompt / tools | Harness | AgentExecutor | 不得默认含 secret |
| Credential material | 宿主 store | 仅获准 Adapter 进程 | 投影最小集；不进 lock/evidence |
| Workspace bytes | Provider mount | Harness/Agent 视图 | path view 限制 |
| Published artifacts | Harness via capability | Evaluation materialize | logical name + allowlist |
| Evaluator raw | task evaluator | Result binder | 独立 materialization |
| Flat Result | Evaluation Core | CLI / evidence / 后期聚合 | status/score/metrics 最小集 |
| Evidence tree | adapters/filesystem | 人类与后续工具 | 无 secret；可定位 raw |

## Platform Boundary（Target）

| 平台能力 | Owner | 备注 |
| --- | --- | --- |
| 本机 process（L0） | Provider adapter | `v0.3` |
| Docker Attempt（L1） | Provider adapter | `v0.8` |
| Codex CLI | AgentExecutor adapter | `v0.6` 竖切 |
| 其他 Agent 后端 | 插件 Executor | `v0.9` |
| DB/浏览器等 | Environment adapter | `v0.10` |
| 宿主持久化 ControlStore | 未定；默认不做 | 勿提前引入 |

## Failure and Privacy Boundary（Target）

| 失败类 | 表现 | 归属 |
| --- | --- | --- |
| 配置/锁失败 | 非 0；无伪 PASS | Config / CLI |
| 未授权 effect | 执行前拒绝 | Capability / Provider |
| Agent 基础设施错误 | runtime failed；可无 score | Runtime / Executor |
| 评测低分 | evaluation fail/score；runtime 可 succeeded | Evaluation |
| Evaluator crash | 明确错误相位 | Evaluation |
| Cleanup 失败 | warning | Provider / Lifecycle |
| 用户取消/超时 | 进入 cleanup | Lifecycle |

隐私：token、`CODEX_HOME` 内容、DB 密码不得出现在 lock、默认日志、evidence 正文。

## Testing and Evidence

| 等级 | 含义 |
| --- | --- |
| `design-only` | 仅文档 / 未跑通真实 Agent 的表面 |
| `runnable-mvp` | 真实 public entrypoint + 真实 Agent（**当前限定** `examples/core/sdk-agent-session` 与 journeys 类；见 `examples/README.md`） |
| `isolated` | 隔离 Attempt + 红线负向 |
| `real-benchmark-verified` | 固定 upstream、限定范围公开 journey |

| 测试层 | 用途 | 不能单独证明 |
| --- | --- | --- |
| unit | 纯规则、schema、状态机 | 产品可运行 |
| integration | adapter 接线、本地 fake | 真实 Codex/上游 |
| e2e / 公开 smoke | production CLI | — |

Fixture 与 mock 不得升级证据等级。

## Change Ownership

| 变更类型 | 首先更新 | 同步 |
| --- | --- | --- |
| 顶层目录、模块所有权、import direction、composition root | **本文** | root/specs `AGENTS.md`、代码 |
| 产品/机制设计、红线、Capability 契约语义 | `docs/design/*`（必要时 PRD） | 本文相关节、Roadmap、Active Spec |
| 实现期用户点名绑定决策 | `specs/constitution/YYYY-MM-DD-*.md` | docs 链接、Spec |
| 版本用户结果与验收勾选 | `specs/ROADMAP.md` | Active Spec、README |
| 实现 delta、失败分支、文件列表、Phase 证据 | 所属 Active Spec | 代码、测试；末 Phase 同步本文/docs |
| CLI 用户入口或公开支持范围 | `README.md` | Roadmap、docs 摘要 |
| 执行期意外选择 | `specs/BLOCKED.md` | 若改权威则同步权威文件 |

## 与设计文档的分工

| 问题 | 读哪里 |
| --- | --- |
| 为什么这样切 Core？ | [docs/design/01](docs/design/01-bora-core.md) |
| `bora.yaml` 字段与 lock？ | [docs/design/02](docs/design/02-task-package-and-config.md) |
| Harness / SDK API 形状？ | [docs/design/03](docs/design/03-harness-layer.md)、[04](docs/design/04-harness-core-sdk.md) |
| Runtime/Agent Service 细节？ | [docs/design/05](docs/design/05-runtime-core.md) |
| 插件与可见性？ | [docs/design/06](docs/design/06-capability-adapter-visibility.md) |
| 评测与失败语义？ | [docs/design/07](docs/design/07-budget-evaluation-failure.md) |
| Owner 矩阵全文？ | [docs/design/09](docs/design/09-owner-matrix-and-structure.md) |
| 源码放哪、谁依赖谁？ | **本文** |
