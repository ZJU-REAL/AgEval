# 实现决策：ACP 统一 Agent Executor 入口

## Metadata

| Field | Value |
| --- | --- |
| Decision date | 2026-08-04 |
| Owner | User review required |
| Status | **draft — pending user review** |
| Scope | coding-agent backend 的 ACP stdio 入口、注册描述、host/L1 镜像 BOM 与 placement、`AgentResult` / evidence 出口 |
| Related issue | [GitHub Issue #3](https://github.com/ffy6511/BORA/issues/3) |
| Related spec | [Spec 19 — ACP 统一 Agent 后端](../active/19-acp-agent-executor-plan.md) |

## Decision Summary

对声明 ACP wire 的 coding-agent backend，BORA 只维护一个标准 ACP JSON-RPC client（跑在 **Parent / Host Runtime**）。Codex、Claude Code、OpenCode、Grok Build、**Pi（via `pi-acp`）** 等差异收敛为数据化 entry descriptor；vendor 私有 CLI stdout 到 ACP 的翻译由外部官方、原生或厂商入口承担。Host 与 Docker L1 复用同一 client；placement 只改变进程启动位置、UID/GID、workdir、network 与 credential projection。

**L1 官方基座必须在 image build 期安装最低验收 entry 的 engine 与 ACP 入口（exact pin）**；Mode 1 必须同时具备 engine 与 adapter（含 **`pi` + `pi-acp`**）。禁止 `bora run` / invoke 时 `npm i` / floating `npx`。

ACP 调用完成后仍归一化为 `AgentResult` 并写入 §8.9 Attempt evidence。Runtime identity、执行前 hard ceiling、Provider 隔离、credential policy、writer barrier、独立 evaluator 与 final PASS authority 均保持不变。

## Problem

当前 `codex`、`pi`、`opencode`、`claude-code` 分别解析私有 CLI stdout，host 与 L1 container 还可能形成两套解析路径。commit `13eed2b` 中 `agent_container._try_parse_structured` 通过反向扫描 JSONL、猜测字段和正则提取 JSON，说明 parse parity 无法靠隔离 smoke 自动保证。

该结构把每个 vendor 私有格式的变化扩散进 BORA。问题位于 Agent Executor **inlet**；`AgentResult`、evidence 与 evaluator **outlet** 所有权没有缺陷。

## Decision

### 统一 wire owner

1. 对 `execution_mode: acp-stdio` 的 backend，BORA Core 只调用一个 ACP client implementation；新增 ACP agent 只增加 entry descriptor、capability/pin 与 conformance evidence。
2. ACP client 只解释标准 ACP initialize、session、prompt、update、cancel/close 与协商能力，不解析 vendor 私有字段，也不含 vendor stdout regex。
3. Vendor 私有协议翻译运行在 BORA 进程之外：Mode 1 adapter package、Mode 2 native ACP subcommand 或 Mode 3 vendor package。
4. Host 与 L1 调用同一 ACP session/result mapper。L1 launcher 只负责 `docker exec` placement 与 process lifecycle，不实现第二个 JSON-RPC client、第二套 event mapper 或 structured-output scraper。
5. ACP entry、engine binary 或协商能力缺失时 fail closed。任何失败都不得回退到同 vendor 的私有 CLI parser、host binary 或 `openai-http`。

### 进程边界（Parent client vs Attempt image）

| 组件 | 运行位置 | 是否进入 `bora-attempt:l1` |
| --- | --- | --- |
| BORA ParentAgentService + **typed ACP client**（Python `agent-client-protocol` 等） | Host / parent process | **否** |
| ACP entry 进程（`codex-acp`、`claude-agent-acp`、`opencode acp`、`grok agent stdio`…） | Host 子进程，或 L1 container 内 `docker exec` | **是（L1 必装最低集）** |
| Vendor engine（`codex`、`claude`…） | 与 Mode 1 entry 同侧 | Mode 1：**与 adapter 同装** |
| Credential 值 | Host 投影进 child env | 永不 bake 进镜像层或 lock |

JSON-RPC 在 parent 与 ACP entry 的 **stdio** 之间进行（L1 经 `docker exec` 附着同一 entry 的 stdin/stdout）。Attempt 镜像 **不** 安装 BORA 的 Python ACP SDK。

### Entry descriptor

Entry descriptor 是 mechanism registry 数据，至少记录：稳定 `entry_id`、integration mode、ACP command/args、可选 engine detect command、只作文档的 install command、exact package/binary version、credential locator allowlist 与 readiness probe。三种 mode 共用同一 schema 和 client，不成为三套 Core subsystem。

Runtime 不在 invoke 时联网发现 registry 或执行安装。`install_command` 不得由 `bora run` 自动执行。Lock/evidence 记录 descriptor digest、entry id、版本、ACP protocol version 与 execution location，不记录 credential value。

### L1 官方基座 BOM（必须 bake-in）

官方基座 `bora-attempt:l1`（`docker/attempt`）在 **build 期**安装与 Spec 19 pin 表一致的最低验收集。`build.py` digest 必须覆盖 Dockerfile、`install-executors.sh` 与 pin lock 文件，禁止只 digest Dockerfile。

| Mode | `entry_id` | Engine（detect / pin 族） | ACP entry（command） | L1 bake-in |
| --- | --- | --- | --- | --- |
| 1 | `codex` | `codex`（exact engine pin） | `codex-acp`（exact `@agentclientprotocol/codex-acp`） | **engine + adapter** |
| 1 | `claude-code` | `claude` / `claude-code` | `claude-agent-acp`（exact `@agentclientprotocol/claude-agent-acp`） | **engine + adapter** |
| 1 | `pi` | `pi`（exact engine pin，如 `@earendil-works/pi-coding-agent`） | `pi-acp`（exact npm `pi-acp`；官方 [ACP registry](https://github.com/agentclientprotocol/registry) id `pi-acp`，**非** `@agentclientprotocol/*` org 包名） | **engine + adapter** |
| 2 | `opencode` | `opencode`（exact binary，含 `acp` 子命令） | `opencode acp`（无独立 adapter 包） | **CLI only** |
| 3 | `grok-build` | detect 可用 `grok` | `grok agent stdio`（exact `@xai-official/grok`，**非** invoke 时 `npx latest`） | **vendor entry pin** |

附加规则：

1. **最低五 entry 进入官方基座**（Codex、Claude、Pi、OpenCode、Grok；与 Spec 19 host smoke 对齐）。package `environment/Dockerfile` 默认 `FROM bora-attempt:l1`，**不得**覆盖 registry 的 command/version/install；不得引入 floating tag。
2. Mode 1 镜像内缺 engine 或 adapter → image build 或 preflight 失败（`adapter-missing` / `engine-missing`），禁止改走私有 `codex exec` / `pi --mode json` scrape。
3. ACP 与 engine 二进制必须落在 **numeric non-root actor 可读的 PATH**（例如 `/usr/local/bin`）；Phase 验收要求以 actor UID 执行 `command -v <acp-entry>` 成功。
4. 镜像 **不** bake credential、auth file 或 account state；auth 仍靠 Runtime 投影。
5. 迁移完成前，私有 `executor: pi` stdout 路径可作 **temporary residual**；**Target** 为 `executor: acp` + `options.entry: pi`。不得把「有 `pi` 无 `pi-acp`」标为 ACP ready。
6. Host 操作者显式安装 **同一 exact pin**；inventory 分别报告 `engine_ready` 与 `acp_entry_ready`。

Exact 版本号以 [Spec 19](../active/19-acp-agent-executor-plan.md) pin 表与 `docker/attempt/acp-entries.lock.json`（实施后）为单一来源；本文件只冻结 **必须装什么类别**，不在此复制会过期的次要版本号。

### Host 与 L1 placement

Host launcher 直接启动 descriptor 的 ACP stdio entry。L1 launcher 在已绑定 `ExecutionTarget` 中以 actor UID/GID、private HOME、locked workdir、network 和 scoped env 启动 **同一 entry command**。两者把 stdin/stdout streams 与 process lifecycle 交给同一 parent ACP client。

Timeout、cancel、relay failure 或 target death 先停止新 effect，发送 ACP cancellation（仍可通信时），随后有界 terminate/kill 并确认 writer stop。无法确认停止时 evaluator barrier 拒绝启动。L1 failure 的 host fallback counter 必须保持零。

### Outlet 与 authority

- `session/update` 等标准 ACP event 进入 per-invocation evidence；请求、事件、最终文本、usage、stop reason、entry/protocol metadata 统一脱敏。
- ACP content 映射到现有 `AgentResult.{text, structured, usage, events, ok, error}`；映射规则由 Spec 19 固定并由所有 entry 共用。
- ACP session id 只属于当前 BORA Attempt/session binding，不可替代 Run/Trial/Attempt/Invocation identity，也不可跨 Attempt 恢复。
- ACP trajectory 只提供观察与复盘。`HarnessTerminal.completed`、ACP `end_turn` 或完整 trajectory 都不形成 PASS。

### 已由 Spec 19 固定的局部选择（批准 Spec 后生效）

下列项 **不再作为开放问题**；实现以 Spec 19 Decision Summary 为准：

| 项 | Spec 19 裁决 |
| --- | --- |
| Public profile | `executor: acp` + `options.entry`；无 vendor alias 兼容层 |
| Protocol surface | initialize / session new·prompt·cancel·close + updates；permission → cancelled |
| Structured | 完整 final text JSON object 才写 `structured`；禁止 regex scrape |
| Multimodal input | 本增量不支持；收到则 `acp_unsupported_content` |
| Pins / SDK | Spec 19 exact pin 表 + Python `agent-client-protocol` 固定版本 |
| `pi` | **纳入最低 ACP 集**（Mode 1：`pi` + `pi-acp`）；私有 stdout 仅迁移期 residual |

## Non-decisions

本决策不要求用 ACP 替换 `openai-http`，不把 ACP 变成 Harness↔Runtime Capability transport，不引入 IDE 交互式 permission UX、跨 Attempt resume、插件市场或动态远程 registry。Gemini/Qoder 等可复用同一 descriptor 机制扩展，但不进入本决策最低 acceptance。

**Pi ACP 证据（2026-08-04）：** 官方 agents 列表与 [agentclientprotocol/registry `pi-acp`](https://github.com/agentclientprotocol/registry) 登记 `pi-acp`；npm 包名 `pi-acp`（起草时 pin 见 Spec 19）；桥接 `pi --mode rpc`（见 [svkozak/pi-acp](https://github.com/svkozak/pi-acp)）。注意：`@junghanacs/pi-shell-acp` 是 **反向**（pi 调用其它 ACP backend），**不是** BORA 所需的「client→pi」adapter。

## Design and Architecture Relationship

本文件记录实现期绑定方向，不替代设计权威。实施前必须先同步：

| Artifact | Required synchronization |
| --- | --- |
| [docs/design/05-runtime-core.md](../../docs/design/05-runtime-core.md#84-agent-capabilityagent-service-与多后端切换) | ACP inlet、parent client、L1 BOM、`AgentResult`/evidence 保持 |
| [docs/design/02-task-package-and-config.md](../../docs/design/02-task-package-and-config.md) | `executor: acp` + `options.entry`、官方基座预装 |
| [docs/design/06-capability-adapter-visibility.md](../../docs/design/06-capability-adapter-visibility.md) | Adapter admission、无 fallback、credential projection |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | `agent_acp` / registry / container launcher 结构 |
| [specs/ROADMAP.md](../ROADMAP.md) | 未勾选的 ACP outcome；不得由规划直接勾完成 |

若与 `docs/` 冲突，先停实现并由用户决定是否改设计权威。

## Red Lines

- 禁止在 ACP client、L1 launcher 或 entry registry 中加入 vendor private stdout field guessing、reverse JSONL scan 或正则 JSON scrape。
- 禁止因 ACP entry/engine/credential/capability 缺失而切换到 private CLI、host binary、其它 profile 或 `openai-http`。
- 禁止把 install command 当作运行时副作用；`bora run` 不执行 npm/pip install，不获取 floating `latest`。
- 禁止 L1 镜像只装 engine 不装 Mode 1 adapter，或 invoke 时再装 adapter。
- 禁止把 Python ACP SDK 或 BORA parent client 塞进 Attempt 镜像冒充「容器内统一」。
- 禁止把 host credential、token、auth file bytes、Authorization/cookie、ACP auth payload 写入 lock、stdout、trajectory、workspace、example 或 image layer。
- 禁止向 Harness/Agent 暴露 Docker handle、socket、raw target mapping 或 host HOME。
- 禁止让 ACP SDK、entry package 或 session id 成为 Core identity、hard-ceiling、effect、cleanup、evaluator 或 PASS authority。
- 禁止把 ACP transport 描述成 Harness Capability transport，或从 ACP journey 推导全 suite `isolated` / `real-benchmark-verified`。

## Integration Mode Registry

| Mode | `entry_id` | Engine detect | ACP entry command | Install responsibility | Required readiness |
| --- | --- | --- | --- | --- | --- |
| Mode 1 | `codex` | `codex` | `codex-acp` | Host 与 **L1 build** 同 exact `@agentclientprotocol/codex-acp` + engine pin | engine ∧ ACP entry；缺 entry → `adapter-missing` |
| Mode 1 | `claude-code` | `claude` | `claude-agent-acp` | Host 与 **L1 build** 同 exact `@agentclientprotocol/claude-agent-acp` + engine pin | 同上 |
| Mode 1 | `pi` | `pi` | `pi-acp` | Host 与 **L1 build** 同 exact npm `pi-acp` + engine pin | 同上 |
| Mode 2 | `opencode` | `opencode` | `opencode acp` | Host 与 **L1 build** exact OpenCode binary | binary + initialize/session probe |
| Mode 3 | `grok-build` | `grok`（可选） | `grok agent stdio` | Host 与 **L1 build** exact `@xai-official/grok` pin | pinned entry + initialize/session probe |

## Alternatives

| Alternative | Decision |
| --- | --- |
| 继续维护每个 vendor 的 Python stdout parser | 拒绝 |
| 为每个 integration mode 写独立 client | 拒绝；mode 只决定 entry 供应 |
| L1 只装私有 CLI，host 改 ACP | 拒绝；保留第二套解析 |
| L1 运行时 `npx` 拉 adapter | 拒绝；不可复现且违反 no-runtime-install |
| 把 ACP client 放进 container、parent 只 docker exec 裸 CLI | 拒绝首选；client 留 parent，entry 在 container，stdio 附着 |
| 全改 `openai-http` | 拒绝；coding-agent 语义不同 |

## History

| Date | Change | Reason |
| --- | --- | --- |
| 2026-08-04 | 创建 draft | Issue #3 |
| 2026-08-04 | 收口 Open Q 到 Spec 19；显式 L1 BOM、parent client 边界、Mode 1 双装、PATH/no-runtime-install | 审查补全 Docker/ACP 适配器 bake-in 与文档可执行性 |
| 2026-08-04 | 最低集纳入 Pi：Mode 1 `pi` + `pi-acp`（registry/npm 已证实） | 用户要求；官方 ACP registry 已登记 |
