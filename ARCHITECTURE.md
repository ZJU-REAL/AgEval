# ageval Architecture

本文只维护**实现结构**：当前 vs 目标布局、模块所有权、依赖方向、composition root、运行生命周期、跨边界数据流、失败/清理归属、证据分类与变更同步。

- **不**写产品长文、版本勾选清单、Phase 任务表。
- 产品与机制设计权威：[docs/](docs/README.md)（尤其 [docs/design/](docs/design/)）。**自包含**；不要读仓外 BRIEF。
- 增量交付与验收跟踪：[GitHub Issues](https://github.com/ZJU-REAL/BORA/issues)。
- 读者向文档：[website/](website/)（非设计权威）。

GitHub 仓库路径目前仍是 `ZJU-REAL/BORA`。产品名、包、CLI 是 **ageval**。

## Document Status

| 字段 | 值 |
| --- | --- |
| 产品 | ageval（agent eval） |
| 实现状态 | Attempt 五相位已接；盒子 kind `local` / `docker` / `e2b` / `ssh`；公开命令以 `ageval --help` 为准 |
| 证据等级 | **限定 `runnable-mvp`**：local ACP、docker ACP、点名 journeys 已有公开 run。e2b/ssh **代码在、缺钥则 skip，不得标 isolated** |
| 设计权威 | [docs/README.md](docs/README.md) |
| 结构权威 | **本文** |
| 近端目标结构依据 | [docs/design/00](docs/design/00-overview-and-product.md)、[docs/design/01](docs/design/01-ageval-core.md)、[docs/design/09](docs/design/09-owner-matrix-and-structure.md) |
| 更新触发 | 见文末 [Change Ownership](#change-ownership) |

**禁止**把下方 Target 树或流程图当作「已实现」。Current 与 Target 必须分开阅读。

## System Overview

ageval 锁定一份 **dataset**，打开一个 **盒子**（独占槽 `environment`），在可见 Attempt 流水线里跑题包 `run.py`，writers 停止后由独立 `evaluator.py` 出分并绑定扁平 Result。

Coding agent 经 parent **ACP** client + `host.attach_stdio` 进入盒子。其它执行机制以 `ageval.plugin/1` 填独占槽 `executor`。

### 主要参与者

| 参与者 | 职责 | 不负责 |
| --- | --- | --- |
| 操作者 / CLI | 发起 lock/run/inspect，读 exit code 与摘要 | 业务 workflow、评分算法 |
| Application | use case 编排、**唯一 composition root** | 框架无关领域规则的第二份实现 |
| Config | `load_and_lock` → `LockedTaskConfig` + `extension_bindings` | 解释 Python workflow |
| Attempt 宿主 | `run_attempt`：environment → run → evaluate → record；`finally` cleanup | 厂商 SDK、题 loop |
| 盒子（environment 赢家） | `preflight` / `start` / `exec` / `upload` / `download` / `attach_stdio` / `stop` | ACP 协议、PASS |
| Capability | 向 `run.py` 暴露已授权操作面 | 颁发 final PASS |
| Evaluation | barrier、盒内 evaluator、`bind_evaluation`、evidence | 统一所有评分算法 |
| SDK（`ageval_sdk`） | `RunContext`、`AgentSession`、Tool 软限 | Run identity、凭据、verdict |
| 题包 `run.py` | 业务 loop、本地 Tool、`ctx.params` | Docker / 凭据 / final PASS |
| Plugins | 独占槽 / 链槽实现；`src/ageval/plugins/` 注册表 + first-party contrib | 按 Benchmark 名分支；第二套 resolve |
| Evaluator（package） | task truth | 启动 Agent、持有 host secret |

### 目标数据/控制主流（validated output 方向）

```text
dataset 根 (ageval.yaml / ageval.dataset/1)
  → resolve_task(--task) → tasks/<id>/task.yaml
  → 合并 profiles.yaml（environment + agent_profiles）
  → load_and_lock → LockedTaskConfig + extension_bindings + digest
  → IdentityFactory：Run / Trial / Attempt + evidence 根
  → host.preflight
  → run_attempt
       environment  host.start → upload data/ → after_environment_ready → environment_setup
       run          子进程 run.py ← Agent Service socket ← attach_stdio
       evaluate     停 writer → upload evaluation/ → 盒内 evaluator.py → bind
       record       trajectory_collect → 引擎写 trajectory.jsonl
       finally      cleanup → host.stop
  → .ageval/runs/<attempt_id>/
```

箭头含义：**控制流推进**。跨信任边界的数据流见 [Data Flow](#data-flowcurrent)。

## Runnable System Path

### Current（已验证公开命令）

| 项 | 值 |
| --- | --- |
| Public entrypoint | `ageval lock` / `run`（含 `--probe`）/ `tasks` / `campaign` / `view` / `plugin` / `evidence` / `status` / `cancel` / `executors` / `jobs` / `results` / `publish` / `release` / `agent` / `registry`（以 CLI 为准） |
| Production composition root | `src/ageval/application/composition.py` |
| Smoke lock | `uv run ageval lock examples/core --task config-minimal`（exit 0，摘要含 `dataset_id`，无 `database_id`） |
| Smoke local ACP | `uv run ageval run examples/core --task acp-local-min` |
| Smoke docker ACP | `uv run ageval run examples/core --task acp-docker-min --profiles examples/core/profiles.docker.yaml` |
| Smoke journeys | `uv run ageval run examples/journeys --task terminal-jsonl-agg`；`… --task env-postgres-min` |
| Expected failure | 未知 format → `invalid_format` exit 2；缺 `--task` 视 CLI；e2b/ssh 缺钥 `--probe` `ready:false` |
| Observable result | 无 secret 的 lock summary + digest；Attempt 有 `lock.json` / `result.json` / `trajectory.jsonl` |
| 证据等级 | **限定 `runnable-mvp`**（上列公开命令；不得从文档推导升级） |

文档变更建议：

```bash
git diff --check
# website 变更时：pnpm --dir website build
```

### Target — 未宣称完成的结构/证据

| 项 | 计划值 |
| --- | --- |
| e2b / ssh 真 ACP | 同一题 `environment: e2b` 与 ssh A+B 公开 `ageval run`（有凭证才勾）。缺钥 skip ≠ 通过。Protocol seam 需要第二个真实云赢家 |
| 外置插件真跑 | nooa / dsh 各一条真 `ageval run`；miniswe 至少 lock。install 认得 ≠ 真跑 |
| 树核对 | `plugins/defaults` 与 `contrib/defaults` 不要两套；CLI 只 import composition |
| 点名示例硬切 | [docs/design/10](docs/design/10-examples-database-52.md) 列出的 lock/run；旧 format 留在树里必须 lock 失败 |
| 文档 | 本文 Current = `src/ageval` + 五相位 |

更早的中间检查点以代码与 examples 为准。**禁止**把 Target 当 Current。

## Source Layout

### Current Source Layout

```text
ageval/                              # GitHub 仓路径仍为 ZJU-REAL/BORA
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── pyproject.toml                   # name = "ageval"；script ageval =
├── uv.lock
├── src/ageval/
│   ├── cli/                         # Typer：argv、help、exit code
│   ├── application/
│   │   ├── composition.py           # CLI 只从此处 import builders
│   │   ├── lock.py                  # load_and_lock + 能力/inject 图
│   │   ├── run.py                   # 铸造 identity → ctx → run_attempt
│   │   ├── campaign.py
│   │   ├── suite/                   # suite_run、fingerprint、suite_metrics
│   │   ├── registry_ops/            # results / publish / login / org / list
│   │   ├── plugin_ops/
│   │   ├── agent_ops/               # --agent 投影进 profiles
│   │   └── local_jobs/              # 本机 Job 删除
│   ├── attempt/                     # 深模块：一次 Attempt 的可见流水线
│   │   ├── __init__.py              # run_attempt 五行相位
│   │   ├── ctx.py
│   │   ├── emit.py                  # 链槽 next()
│   │   └── phases/
│   │       ├── environment.py
│   │       ├── run.py
│   │       ├── evaluate.py
│   │       ├── record.py
│   │       └── cleanup.py
│   ├── config/                      # dataset 根 + task.yaml + profiles
│   ├── environments/
│   │   ├── protocol.py              # EnvironmentProvider · StdioTransport · caps
│   │   └── streams.py
│   ├── plugins/
│   │   ├── slots.py                 # exclusive / chain id
│   │   ├── registry.py / resolve.py / bootstrap.py
│   │   ├── defaults/                # environment_setup 认 setup.sh
│   │   └── contrib/
│   │       ├── acp/                 # 独占槽 executor + attach_stdio client
│   │       ├── docker/              # 独占槽 environment
│   │       ├── local/
│   │       ├── e2b/
│   │       ├── ssh/                 # A 整机 / B 远端容器
│   │       └── openai_http/
│   ├── runtime/
│   │   ├── identity.py
│   │   ├── parent_agent.py          # 只认 executor 服务 + host.attach_stdio
│   │   ├── task_launch.py           # 控制面子进程跑 run.py
│   │   └── task_worker.py
│   ├── evaluation/                  # barrier + 盒内 runner + bind PASS
│   ├── evidence/                    # 布局字符串的唯一主人
│   ├── capabilities/
│   ├── registry/                    # Hub 客户端
│   ├── viewer/                      # 本地 Jobs HTTP
│   ├── control/
│   └── agents/
├── sdk/python/src/ageval_sdk/       # RunContext / RunTerminal / AgentSession
├── apps/
│   ├── viewer/                      # `ageval view` SPA
│   └── hub/                         # Registry Dataset / Plugin / Agent / Leaderboard
├── services/registry/               # 独立 HTTP：Route.access + *Service
│   ├── app.py / http_api.py / asgi.py / backend.py
│   ├── auth_service.py / package_service.py / result_service.py / org_service.py
│   ├── queries.py / dataset.py / sql_adapter.py / store.py
│   └── routes.py                    # ROUTES 必须声明 access
├── examples/
│   ├── core/                        # acp-local-min / acp-docker-min / …
│   ├── journeys/                    # terminal-jsonl-agg / env-postgres-min / …
│   ├── l1/                          # docker topology 示例（多 group 真调度不承诺）
│   ├── tau3-airline/                # airline-00 lock
│   └── agents/
├── plugins/                         # 外置 ageval.plugin/1
│   ├── nooa/ / dsh/ / miniswe/
│   ├── home-files/ / agent-skills/
│   └── slot-probe/
├── docker/attempt/                  # 官方基座：ACP entries bake-in
├── tests/
├── docs/
└── website/
```

Hub Agent appearances 是官方公开 suite 行上 `job_overlay.agent_ref` 的**派生视图**，不是 Core 对象。没有 `/runtimes` 产品面。

Production Attempt：`application/run.py` 铸造 identity 一次，然后 `attempt.run_attempt`。cleanup 在 `try/finally`。Parent Agent Service 与硬顶共享同一配额对象。

### Target Source Layout（尚未全部兑现）

以下是接受的方向，**不是**把 Current 再拆回 `adapters/` + `run_l0.py`。

```text
src/ageval/
  cli/ application/ attempt/phases/ config/
  environments/protocol.py          # 仍无厂商 SDK
  plugins/contrib/{acp,docker,local,e2b,ssh,openai_http}
  plugins/defaults/                 # 或迁到 contrib/defaults，二选一，不要两套
  runtime/{identity,parent_agent,task_launch,task_worker}
  evaluation/{bind,package_evaluator,box_runner}
  evidence/{locators,store,trajectory}
```

**刻意不建（Current 已删除，Target 也不得回潮）：**

- `environment/manager.py`
- `adapters/` 大杂烩、`agent_container.wrap_docker_exec`
- 分叉的生命周期模块（Attempt 只走 `attempt/phases/`）
- 产品 `executor: mock` / FakeHost

### 生成物（非源码所有权）

| 路径/模式 | 说明 |
| --- | --- |
| `.ageval/` | runs、suite-runs、本机 plugin cache、credentials |
| `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` | 工具链 |
| `dist/`、`*.egg-info/` | 构建产物 |

## Module Ownership（Current）

| 路径 | 唯一责任 | 不负责 |
| --- | --- | --- |
| `cli/` | argv、帮助、exit code | 读题包业务、启 Docker、拼 evidence 路径 |
| `application/` | lock/run/campaign/suite/registry/plugin/agent/jobs；**装配** | 把业务规则藏在 bootstrap 外的全局单例 |
| `application/composition.py` | 唯一 production `build_*` | 业务算法 |
| `config/` | dataset resolve；读 `task.yaml` / profiles；digest | 执行 `run.py`、评测 |
| `attempt/` | 相位序、`emit`、AttemptCtx | 厂商 SDK、`container_id` |
| `environments/` | Protocol + caps + 流形状 | `import e2b` / `docker` / `paramiko` |
| `plugins/contrib/docker/` | `docker exec`、compose、uid/gid、镜像 | ACP 协议 |
| `plugins/contrib/e2b/` | E2B SDK、template alias（缓存在该账号，Core 不实现） | Core 缓存层 |
| `plugins/contrib/ssh/` | ssh A/B、`ssh -T` / `docker exec` | 本机假 agent |
| `plugins/contrib/acp/` | parent ACP client、entry registry、`attach_stdio` 消费方 | 层 C writer；vendor stdout scrape |
| `plugins/defaults/` | `environment_setup` 认 `setup.sh`；`evaluation_runtime` / `trajectory_seal` 默认赢家 | 假 executor；PASS |
| `runtime/` | identity、parent Agent Service、task worker 子进程、取消/超时 | 盒子实现、评分 |
| `evaluation/` | barrier 顺序、盒内 runner、扁平 Result | 题包评分算法 |
| `evidence/` | store / redaction / 层 C `trajectory.jsonl` | vendor 协议解析；PASS |
| `registry/` + `services/registry/` | PackageRef、publish、verified cache；独立 HTTP | PASS；把 store credential 交给 CLI |
| `ageval_sdk` | 题包类型与薄 helper | Control Plane 内部类型、verdict |
| `examples/` | 可信回归 dataset | 声称支持完整 upstream suite |
| `tests/` | 契约与回归 | 成为 production composition root |
| `docs/` | 设计与产品规格 | 版本勾选状态 |
| `website/` | 读者向用法 | 设计权威 |

## Dependency Direction

依赖箭头 = **Python import 允许方向**。

```text
cli ──────────────► application.composition
                         │
                         ├─► config / attempt / runtime / capabilities / evaluation
                         │
                         └─► plugins.bootstrap ──► contrib/* ──► environments.protocol
                                                    （contrib 不反向被 protocol import）

ageval_sdk ──► 仅最小公开 DTO / 协议形状
               （禁止 import application、contrib 内部、Control Plane 私有模块）
```

### 禁止

- `environments/protocol.py` 依赖 Typer、Docker SDK、e2b SDK、SQLAlchemy。
- CLI 直接调用 Codex、直接写 evidence 树、直接解析题包业务；CLI 绕过 composition。
- Control Plane import/execute 题包 `run.py` / `evaluator.py` **作为 Python 模块**（必须进程或适配器边界）。
- SDK 取得 host credential 文件内容、Docker socket 控制面、final-result 发布权。
- 在 composition root **之外**隐式注册全局 Adapter 单例。
- 适配器根据 Benchmark 名称、task id、upstream 品牌选择行为。
- ACP / `attempt` / `run.py` 出现 `container_id`、`if kind == e2b`。
- 第二套 `resolve_executor` / CLI 旁路 / application 里手 new Docker。
- 测试 helper 被 production 代码 import 作为唯一装配路径。

第三方 workflow SDK：仅允许题包或**明确**的外置 plugin 依赖；不得反向成为 Core authority。

## Composition Root

| 项 | 规则 |
| --- | --- |
| 唯一生产装配点 | `src/ageval/application/composition.py` 的 `build_*` |
| 新公开 usecase | 必须有对应 `build_*` |
| CLI | 只 import `ageval.application.composition`（及 `ageval.cli` 自己） |
| 测试 | 可有测试专用 wiring；公开 smoke 必须走 production CLI |
| 插件发现 | 扩展注册表 + `ageval plugin install` 本地 cache；失败 fail-closed；禁止 `ageval.agent_executors` dual path |

## Extension emit map（Current）

Host **awaits** 已注册的链槽 / 独占赢家。插件经 `(ctx, value, nxt)` 改写或短路，**不是**丢声明行给 Core 事后解释。

槽名权威：`src/ageval/plugins/slots.py`。只有 **exclusive** 与 **chain** 两种。Current 独占槽：`environment`、`executor`、`evaluation_runtime`、`trajectory_seal`。后两者默认赢家是引擎（`plugin_id: default`）。PASS 仍只经 `bind_evaluation` 进入 Result；`evaluation_runtime` 返回 raw，不得自己写 verdict。`pass` / `identity` / `cleanup` / `evidence` 不是服务。

```text
environment phase
  before_environment
  host.start
  upload data/ → /attempt/workspace
  after_environment_ready      # ACP which / 探测再装
  environment_setup            # setup.sh（defaults）
  after_environment

run phase
  before_run
  子进程 python -m ageval.runtime.task_worker → run.py
    Agent.session → unix socket → ParentAgentService
      before/after_agent_open
      before_agent_invoke → executor.invoke(attach_stdio) → after_agent_invoke
      normalize_agent_result
      before/after_agent_close
  stop Agent Service；mark_writers_stopped
  after_run

evaluate phase
  before_evaluate
  upload evaluation/           # gold 此刻才进盒（引擎代码，不挂槽）
  evaluation_runtime.evaluate  # 独占槽赢家；默认盒内 evaluator.py
  bind_evaluation              # PASS 只在这里进 Result
  after_evaluate               # 不得改 status

record phase
  trajectory_collect → enrich  # fail-open 链
  trajectory_seal              # 独占槽赢家写 trajectory.jsonl（层 C）

cleanup (finally)
  cleanup_report
  host.stop
```

`FAIL_OPEN_SLOTS`：`before_run` / `after_run` / `trajectory_collect` / `trajectory_enrich` / `cleanup_report`。其余槽失败即该相位失败。

## Lifecycle（Current）

### 外层状态（Attempt）

```text
created
  → locking          # load_and_lock
  → preflight        # host.preflight；缺钥在此失败
  → environment      # start + seed + setup
  → run              # run.py + ACP
  → evaluate         # 停写 + gold + bind
  → record
  → cleanup          # finally，任何失败路径都进
  → terminal         # PASS | FAIL | ERROR
```

### 顺序不变量

1. 未 `load_and_lock` 成功不得 `start` 盒子、不得 invoke。
2. Evaluator 不得与可写 Agent/`run.py` writer 并发面对同一评测输入。gold 在 evaluate 开头才 upload。
3. `cleanup` 必须可从超时/取消/异常进入；cleanup 失败 → warning，不覆盖已 bind 的 score。
4. retry / 重跑 → **新 Attempt**，不静默改写旧 Attempt identity。一次 Attempt 只 `IdentityFactory.new_run` 一次。
5. Campaign 只调度 Trial/格点，不与 `run.py` 内 workflow 合并。

详细相位见 [docs/design/05-runtime/lifecycle.md](docs/design/05-runtime/lifecycle.md)。

## Data Flow（Current）

| 数据 | 生产者 | 消费者 | 边界规则 |
| --- | --- | --- | --- |
| `ageval.yaml` + `task.yaml` + `profiles.yaml` | 作者 / CLI | Config | 唯一规范读取；未知 format 一个错误 |
| `LockedTaskConfig` + `extension_bindings` | Config | Attempt、盒子、executor、Evaluation | 可复盘；无 secret 明文 |
| `ctx.params` | Config 投影 | `run.py` | 只读；无 gold/credential |
| Agent prompt / tools | `run.py` | ACP / 其它 executor | 不得默认含 secret |
| Credential material | 宿主 env | 仅获准 executor 子进程 | locator；不进 lock/evidence |
| Workspace bytes | 盒子 upload/bind | Agent 与 `run.py` 可见面 | 合同路径 `/attempt/workspace` |
| Published artifacts | `ctx.publish_json` | evaluate materialize | logical name + allowlist |
| Evaluator raw | 题包 `evaluator.py` | `bind_evaluation` | 独立 materialization；同盒 |
| Flat Result | Evaluation | CLI / evidence / 聚合 | `status`/`score`/`kind`/`logs` |
| Evidence tree | `evidence/` | 人类与后续工具 | 无 secret；可定位 |

## Platform Boundary（Current）

| 平台能力 | Owner | 备注 |
| --- | --- | --- |
| `environment: local` | `plugins/contrib/local` | 真目录 |
| `environment: docker` | `plugins/contrib/docker` | 真容器；compose / uid_gid / path_views |
| `environment: e2b` | `plugins/contrib/e2b` | SDK 只在本包；缺 `E2B_API_KEY` preflight 失败 |
| `environment: ssh` A/B | `plugins/contrib/ssh` | A 无 image；B 有远端 tag |
| ACP coding-agent | `plugins/contrib/acp` | 唯一 coding-agent inlet；`attach_stdio` |
| 其他 Agent 后端 | `openai-http` / 外置 `nooa` `dsh` | 非 vendor stdout scrape |
| 官方基座镜像 | `docker/attempt/` | build 期 bake ACP entries；invoke 禁止 `npm i` |
| Registry HTTP | `services/registry/` | Handler 不直接 `state.meta` |

## Failure and Privacy Boundary

| 失败类 | 表现 | 归属 |
| --- | --- | --- |
| 配置/锁失败 | 非 0；无伪 PASS | Config / CLI |
| 未知 format | `invalid_format` 于 `/format` | Config |
| 缺 cap / 缺 inject | lock 失败 | Config / plugins |
| 缺钥（e2b/ssh/ACP） | preflight 或 invoke 一次失败 | 盒子 / executor |
| 未授权 effect | 执行前拒绝 | Capability / 盒子 |
| Agent 基础设施错误 | ERROR；可无 score | runtime / executor |
| 评测低分 | FAIL + score；Attempt 仍完整 | Evaluation |
| Evaluator crash | `error.phase = evaluate` | Evaluation |
| Cleanup 失败 | warning | 盒子 / Attempt |
| 用户取消/超时 | 进入 cleanup | Attempt / runtime |

隐私：token、`CODEX_HOME` 内容、DB 密码、SSH 私钥不得出现在 lock、默认日志、evidence 正文。

## Testing and Evidence

| 等级 | 含义 | 何时可声称 |
| --- | --- | --- |
| `design-only` | 仅文档 | 未被公开 smoke 覆盖的路径（含 e2b/ssh 真跑，在无钥时） |
| `runnable-mvp` | 真实 public entrypoint + 真实 Agent | 有对应公开 journey（当前：core local/docker ACP、journeys 点名题） |
| `isolated` | 隔离 Attempt + 隔离红线 | 有对应验收证据；不得从 docker 一次 PASS 推导 |
| `real-benchmark-verified` | 固定 upstream + 限定范围公开 journey | 有对应验收；不得扩成全 suite |

| 测试层 | 用途 | 不能单独证明 |
| --- | --- | --- |
| unit | 纯规则、schema、相位 | 产品可运行 |
| integration | 接线 | 真实 ACP / E2B / SSH |
| e2e / 公开 smoke | production CLI | — |

Fixture 与 mock 不得升级证据等级。`AGEVAL_SKIP_REAL_ACP=1` 只表示 CI 没跑这条。

## Change Ownership

| 变更类型 | 首先更新 | 同步 |
| --- | --- | --- |
| 顶层目录、模块所有权、import direction、composition root | **本文** | 根 `AGENTS.md`、代码 |
| 产品/机制设计、红线、盒子 Protocol | `docs/design/*`（必要时 PRD） | 本文相关节、Issues、website |
| 实现期用户点名绑定决策 | 写入相关 `docs/design/*` 或 `AGENTS.md` 红线 | 代码、Issues |
| 增量交付与验收跟踪 | GitHub Issues | PR、smoke、README 状态 |
| 实现 delta 与证据 | 代码 / 测试 / 公开 smoke | Issues |
| CLI 用户入口或公开支持范围 | `README.md` + `website/` | docs 摘要 |
| 读者向用法（CLI / Viewer / Hub） | `website/` | 与 docs 冲突时以 docs 为准 |

## 与设计文档的分工

| 问题 | 读哪里 |
| --- | --- |
| 产品故事 / 命名 / 非目标？ | [docs/design/00](docs/design/00-overview-and-product.md) |
| 为什么这样切 Core / 五相位？ | [docs/design/01](docs/design/01-ageval-core.md) |
| `ageval.yaml` 字段与 lock？ | [docs/design/02](docs/design/02-task-package-and-config.md) |
| `run.py` / SDK API？ | [docs/design/03](docs/design/03-task-run-and-sdk.md) |
| 盒子 kind / ACP / evaluate / evidence？ | [docs/design/05-runtime/](docs/design/05-runtime/) |
| 插件独占/链？ | [docs/design/11](docs/design/11-extension-plugins.md) |
| 评测与失败语义？ | [docs/design/07](docs/design/07-budget-evaluation-failure.md) |
| Owner 矩阵全文？ | [docs/design/09](docs/design/09-owner-matrix-and-structure.md) |
| 源码放哪、谁依赖谁、生命周期图？ | **本文** |
