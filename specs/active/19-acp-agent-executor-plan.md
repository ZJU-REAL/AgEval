# Spec 19 — ACP 统一 Agent 后端

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-04 |
| Scope | ACP design/lock/inventory、单一 stdio client、Mode 1/2/3 entries、host/L1 镜像 BOM 与 placement、`AgentResult`/evidence 映射与私有 stdout scrape 迁移 |
| Type | feat |
| Priority | P0 |
| Status | in-progress |
| Planning gate | **closed for product decisions** (2026-08-04 user session)；实施可继续；Phase 勾选仍按证据 |
| Completed | pending |
| Independent review | off |
| Dependencies | [ACP constitution](../constitution/2026-08-04-acp-agent-executor-unification.md) accepted；[Spec 18](18-l1-multi-agent-docker-scheduling-plan.md) SDK/L1 baseline；v0.13–v0.17 trajectory/ceiling baseline；[GitHub Issue #3](https://github.com/ffy6511/BORA/issues/3) |
| Decisions | [Agent Service](../../docs/design/05-runtime-core.md#843-agent-serviceruntime)、[归一化 invoke 契约](../../docs/design/05-runtime-core.md#844-归一化-invoke-契约跨后端)、[Attempt evidence](../../docs/design/05-runtime-core.md#89-attempt-evidence-与-agent-轨迹落盘)、[ACP implementation decision](../constitution/2026-08-04-acp-agent-executor-unification.md#decision) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: 独立验收 subagent + 全量 pytest/回归；通过后可标 Spec completed（**不**勾 Roadmap v0.19 Version Index 除非验收清单齐）。
- **已完成切片（2026-08-04）**：Phase 0–4 — registry/client；host OpenCode/Codex/Pi public PASS；L1 BOM 五 entry；`examples/l1/acp-agent-placement` PASS (`assurance:l1`, `host_fallback_count:0`)。
- Spec 整包尚未 acceptance：Phase 5 private scrape 删除与全 example 迁移、architecture gate、Skills/docs 收口。

### Current blockers

- None

### Potential blockers

- `R1` **closed** — OpenCode public PASS。
- `R2` **closed** — Codex/Claude/Pi Mode 1 public PASS。
- `R3` **closed** — Grok pin `0.2.120` public PASS。
- `R4` **closed** — L1 BOM + `examples/l1/acp-agent-placement` PASS（`host_fallback_count:0`）。

### Local decisions（已接受 — 实施边界）

以下由用户在 2026-08-04 会话确认，**无需再问**：

1. Canonical profile 使用 `executor: acp` + `options.entry: <entry_id>`。`codex`、`opencode`、`claude-code` 不作为 ACP alias；它们在 Phase 5 迁移后不得触发 private parser。`openai-http` 保持独立 `api-client`。
2. BORA 使用 `agent-client-protocol==0.12.0` 的 typed stdio client，并固定 ACP protocol v1 stable surface。禁止手写第二个 JSON-RPC transport/parser。
3. MVP client→agent surface 固定为 `initialize`、`session/new`、可选且标准化的 `session/set_config_option`、`session/prompt`、`session/cancel`、`session/close`；agent→client 消费 `session/update` 与 `session/request_permission`（及 elicitation）。`load/list/fork/resume`、MCP、以及 **client 代持** filesystem/terminal 能力（IDE 式 fs/pty RPC）不在本增量默认路径。
4. **Permission 与可见性分层（用户确认 2026-08-04）：**
   - **物理可见性 / 隔离**：与既有 L0/L1 相同——Provider mount、PathGrant、`docker exec -u uid:gid -w <workspace>`、actor HOME、credential 投影。ACP **不**替代 OS DAC。
   - **`session/request_permission`：batch 默认 auto-approve**（allow / selected 全部通过），evidence 记录每次 decision；**不**弹交互 UI。
   - **Approve 不提权**：ACP approve 只是协议层放行 tool call，**不能**获得 root、`CAP_DAC_OVERRIDE`、或读写未 mount / 对当前 UID 无权限的路径（如 root 私有目录仍 EACCES）。
   - 工具执行落在 **ACP entry 子进程**（L1 即 container 内 actor 身份），不靠 parent 在 host 上代读代写。
   - Client **不**把「完整 IDE filesystem/terminal 代理」作为默认 capability 广告；读写边界靠投影 + 进程身份。
   - `elicitation`（要人类填空）默认 **decline**（batch 无操作员）；与 permission auto-approve 分离。
5. Prompt 仅发送 text content block。输出只拼接有序 `AgentMessageChunk` text；`AgentResult.structured` 只接受完整 trimmed final text 为 JSON object 的 `validated-text`，禁止 substring/reverse-scan/regex 提取。Image/audio/resource 输入延后。
6. Exact initial pins 固定为：Python SDK `0.12.0`；Codex ACP `1.1.9`；Claude ACP `0.64.2`；**Pi ACP `pi-acp@0.0.33`**（官方 registry id `pi-acp`，npm 包名 `pi-acp`，**不是** `@agentclientprotocol/pi-acp`）；OpenCode `1.18.12`；Grok Build `0.2.120`。Engine pin（`pi` / `codex` / `claude` 等）与 adapter pin 写在同一 lock。若 Phase 0 real probe 证明 pin 不可用，按 `BLOCKED.md` 记录并回到用户，不得静默改为其它版本或 floating tag。L1 与 host 使用**同一 pin 表**。
7. **`pi` 纳入最低 ACP 验收集**（Mode 1：`engine=pi` + `acp_entry=pi-acp`）。Target profile：`executor: acp` + `options.entry: pi`。迁移完成前私有 `executor: pi` + stdout parser 仅 temporary residual，**不得** ACP→private fallback。注意勿与 `pi-shell-acp`（pi 调用其它 backend 的反向桥）混淆。
8. **L1 官方基座 bake-in**：`bora-attempt:l1` 在 build 期安装最低 **五** entry 的 engine + ACP 入口（Mode 1 含 codex/claude/**pi** 双装）；`bora run` 永不 runtime install。typed ACP **Python client 只在 parent**，不进 Attempt 镜像。numeric non-root actor 下 ACP command 必须在 PATH 上可执行。package Dockerfile 不得覆盖 pin/command。`session/new.cwd` **必须**等于已投影 workspace 根（容器内绝对路径）。

## Phases

- [x] Phase 0: 设计权威、配置表面与 protocol/pin probe 同步
- [x] Phase 1: ACP entry registry、lock snapshot 与 inventory readiness
- [x] Phase 2: 单一 ACP client MVP（Mode 2 OpenCode）
- [x] Phase 3: Mode 1 Codex/Claude 与 Mode 3 Grok Build
- [x] Phase 4: Docker L1 placement 与 host/container client parity
- [x] Phase 5: 迁移 examples、弃用 vendor private scrape 与状态收口

## Background

### Problem

当前 host 侧 `agent_codex.py`、`agent_pi.py`、`agent_opencode.py`、`agent_claude_code.py` 分别解析私有 CLI stdout；L1 `agent_container.py` 通过 `_cli_argv` 与 `_try_parse_structured` 再实现一次 vendor dispatch 和 heuristic JSON scrape。一次 backend 格式变化需要修改多处 parser，并可能让 host 与 L1 得到不同 `AgentResult`。

### Current Behavior

- `agent_profiles[].executor` 直接使用 `codex` / `pi` / `opencode` / `claude-code` / `openai-http`。
- `executor_capabilities.py` 只有 `cli-process | api-client`，`bora executors` 只区分 host binary 是否在 PATH。
- `agent_registry.py` 为每个 built-in vendor 建 factory；`AgentResult` 定义在 `agent_codex.py`，其它 Adapter 反向 import。
- ParentAgentService 已拥有 Attempt/session binding、invocation hard ceiling、trajectory seal 与 typed failure；Spec 18 已建立 L1 actor→target placement 和 no-host-fallback。
- `openai-http` 是独立 chat/API client，不属于 coding-agent ACP migration。

### Goals and Non-goals

- Goal: 一个 typed ACP client 处理所有 `acp-stdio` entry，并把标准 event/stop/usage 归一为 `AgentResult` + §8.9 evidence。
- Goal: 增加数据化 Mode 1/2/3 registry、descriptor digest、capability/model binding 与 `engine_ready × acp_entry_ready` inventory。
- Goal: 同一 client 在 host 和 Docker L1 运行；placement failure、entry missing、auth/model/protocol failure 全部 fail closed，无 private/host fallback。
- Goal: 可见性继续靠 mount + `docker exec` UID/GID；ACP permission **默认 approve**，且不突破 OS/投影边界。
- Goal: 真实 public smoke 覆盖 Codex、Claude、Pi、OpenCode、Grok；需要凭据的 smoke 可 env-gated，但完成证据必须至少各有一次真实 run。
- Non-goal: 替换 `openai-http`、把 ACP 用作 Harness Capability transport、实现 IDE 交互 permission UI、跨 Attempt resume/reopen、parent 代持 host fs、多模态、动态远程 registry 或插件市场。
- Non-goal: 由本 Spec 提升全 suite `isolated` / `real-benchmark-verified`；ACP trajectory、stop reason 与 Harness terminal 均不决定 PASS。

### Key Insight

Vendor 差异只进入 entry descriptor 和外部 ACP process。BORA 内唯一变化轴是 `AcpProcessLauncher` placement；ACP session lifecycle、event mapping、structured policy、timeout/cancel、redaction 与 `AgentResult` mapping 均只有一份实现。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora executors -v` 与 `uv run bora run <package> --task <task-id>`。
- Production composition root: `src/bora/application/composition.py`；run 路径在 `src/bora/application/run_command.py` 与 `src/bora/application/run_l1.py` 装配 Agent Service/Provider。
- Baseline smokes: `examples/core/sdk-agent-session` 的 L0 multi-invoke、`examples/core/builtin-executor-conformance` 的现有 Codex/Pi/OpenCode profile switch、`examples/l1/sdk-session-single-actor` 的 L1 SDK target placement、`examples/core/evaluator-negative` 的独立 evaluator negative control。
- Observable result: 多 backend、trajectory 与 L1 placement 均已存在；inlet 仍是 vendor private CLI parser，inventory 无 ACP adapter-missing 状态。

### User Story

作为 BORA 操作者，我只选择一个 locked ACP entry，就能让同一 Harness 在 host 或 Docker L1 中调用 Codex、Claude、Pi、OpenCode 或 Grok，并从统一 `AgentResult` 与 evidence 查看标准 ACP 事件；agent 工具在投影 workspace 与 actor UID 权限内运行（permission 默认放行）；entry、credential、model、protocol 或 target 不满足时 run 明确失败，且不会改走私有 parser、宿主 CLI 或突破未 mount 路径。

### Scope Boundary

- Included: `executor: acp` profile schema、entry registry/pin/digest、inventory readiness、typed ACP stdio session、text/validated-text mapping、credential/model preflight、host/L1 launcher、Mode 1/2/3 real smokes、现有 ACP-capable vendor parser migration。
- Deferred: Gemini/Qoder 等新 rows；细粒度 permission deny 策略 / IDE 交互 UI；image/audio/resource prompt；parent 代持 MCP/fs；cross-Attempt resume；ACP v2；dynamic remote registry。
- Compatibility: v2 greenfield 不保留 `executor: codex|opencode|claude-code|pi` 私有 CLI alias。Phase 5 同批迁移仓库 examples/tests 到 `executor: acp` + `options.entry`；`openai-http` 保持 `api-client`。
- Status boundary: 本 Spec 完成只证明列出的 entry/pin/platform journeys 使用统一 ACP client，不扩大 Provider 或 benchmark assurance。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Existing Agent Service/evidence/evaluator baseline | `baseline-verified` | Spec 13–18 accepted production paths | `uv sync --frozen` 后运行 L0 SDK、L1 SDK、trajectory 与 evaluator negative smokes | Parent ceiling/session/trajectory、L1 target、independent evaluator 分别可观察 | 现有 run cleanup；移除测试产生的 `.bora/runs` temp state |
| Accepted ACP implementation decision | `external-accepted` | User；本 Spec `B1` | 用户批准 Constitution、本 Spec local decisions 与 production implementation | Constitution status/history 与本 Spec Planning gate 同步；无未授权 source edit | 不创建运行资源 |
| Typed ACP Python SDK `0.12.0` | `phase-produced` | Agent / Phase 2 | `uv add --exact agent-client-protocol==0.12.0` 并更新 `uv.lock` | SDK golden/fixture client tests、`uv lock --check`、Pyright | 依赖随仓库 lock；无后台进程 |
| Static ACP descriptor registry and pins | `phase-produced` | Agent / Phase 1 | 创建 `src/bora/adapters/acp_entries.json` 与 loader；runtime 不联网发现 | schema/digest/pin parity、unknown/duplicate entry negatives、inventory rows | 无外部资源；registry 只读 |
| OpenCode `1.18.12` native ACP + account | `external-accepted` | User-managed binary/account；Phase 0/2 preflight | Host 显式安装/login；BORA 只投影 locked locator；L1 由 image build exact pin | `opencode --version`、ACP initialize/session/model/prompt real probe、secret scan | 删除 Attempt-private env/HOME；不改 host account |
| Codex ACP `1.1.9`、Claude ACP `0.64.2`、**Pi ACP `pi-acp@0.0.33`** + engines/accounts | `external-accepted` | User-managed engines/accounts；Phase 0/3 preflight | Host 显式安装 exact adapter package；BORA 不运行 install command；L1 build exact pin | engine present、ACP entry present、auth/model/permission/public run；adapter-missing matrix | 删除 Attempt-private auth copies/cache；不修改 host credential source |
| Grok Build `0.2.120` vendor entry + account | `external-accepted` | User-managed xAI account；Phase 0/3 preflight | Host 显式安装 exact package；L1 build exact pin；invoke 使用 `grok agent stdio` | registry/npm pin、initialize/session/prompt real probe、credential/evidence scan | 删除 Attempt-private env/HOME；不保留 npm temp cache |
| Docker Engine/buildx and ACP-enabled L1 image | `external-accepted` | User-owned Docker daemon；Phase 4 consumes it | `docker version`、`docker buildx version`；build repository-owned image | image/platform/digest、entry versions、non-root target、cancel/kill/writer probes | 删除 Spec 创建的 temp container/network/volume/tag；保留 digest evidence |
| ACP fixture servers for deterministic negatives | `phase-produced` | Agent / Phase 2 | `tests/fixtures/acp/` 提供 typed echo、malformed、permission、hang cases | focused tests从 production `AcpExecutor` 进入同一 mapper | test teardown closes pipes and confirms child exit |

</details>

### Runnable Acceptance

- Public entrypoint: `uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="<profile>"'`；`<profile>` 只取下列冻结值：`opencode-acp`、`codex-acp`、`claude-acp`、`pi-acp`、`grok-build-acp`。
- Host success commands:

```bash
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="opencode-acp"'
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="codex-acp"'
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="claude-acp"'
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="pi-acp"'
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance --set '/parameters/active_profile="grok-build-acp"'
```

- L1 success command: `uv run bora run examples/l1/acp-agent-placement --task acp-agent-placement`，至少完成两次 SDK invoke，`execution_location=attempt-container`，`host_fallback_count=0`。
- Expected failure command: `uv run pytest tests/acceptance/test_acp_public_failures.py -q`；通过真实 CLI 子进程分别证明 unknown entry、Mode 1 adapter missing、auth/model unavailable、protocol mismatch、timeout/dead target、**越权路径 EACCES（approve 后仍不可读 root 私有/未 mount）** 均非零或 tool 失败可观测、无 Agent effect fallback 冒充 PASS、Evaluator 规则仍独立。
- Regression commands:

```bash
uv run bora run examples/core/sdk-agent-session --task sdk-agent-session
uv run bora run examples/core/evaluator-negative --task evaluator-negative
uv run bora run examples/core/attempt-trajectory --task attempt-trajectory
uv run bora run examples/l1/sdk-session-single-actor --task sdk-session-single-actor
uv run pytest tests/acceptance/test_builtin_executor_conformance.py tests/acceptance/test_l1_multi_agent_scheduling.py -q
```

- Observable evidence: 每个 invocation 的 metadata 包含 `executor_kind=acp`、`acp_entry_id`、entry version/digest、protocol version、agent info、locked/actual model、stop reason、execution location；events 是有序 ACP updates，final response 与 usage 可解析，全树 secret scan 零命中。
- Verdict boundary: 四个 entry 的 Harness success 仍交给 package evaluator；ACP `end_turn` 只形成 successful Agent result，不能直接形成 Result PASS。

### Extension Seams

- `AcpEntryDescriptor`: 新 agent 通过静态 row 扩展，client 不增 vendor branch；未来 entry-point descriptor plugin 另立 Spec。
- `AcpProcessLauncher`: host subprocess 与 Docker exec 只供应 streams/process lifecycle；未来 VM launcher 可复用 client。
- `AgentResult`: 从 vendor module 移到稳定 contract，ACP 与 `openai-http`/legacy residual 共用 outlet。

## Design

> Inherited design: [Agent Service](../../docs/design/05-runtime-core.md#843-agent-serviceruntime)、[invoke contract](../../docs/design/05-runtime-core.md#844-归一化-invoke-契约跨后端)、[L1 SDK scheduling](../../docs/design/05-runtime-core.md#l1-多-actor-隔离与-sdk-调度面)、[Attempt evidence](../../docs/design/05-runtime-core.md#89-attempt-evidence-与-agent-轨迹落盘)、[ACP constitution draft](../constitution/2026-08-04-acp-agent-executor-unification.md#decision)
>
> Local delta: 将 coding-agent inlet 收敛为 canonical `acp` executor、静态 entry descriptor 与一个 typed ACP client；保留 ParentAgentService、Provider placement、evidence store、Evaluator 与 Result binder authority。

### Canonical Profile and Lock

```yaml
agent_profiles:
  - id: reviewer-codex
    executor: acp
    model: gpt-5.4-mini
    workspace_view: agents
    options:
      entry: codex
```

Validation 与 lock 规则：

- `executor: acp` 必须有 mapping `options`，且 `options.entry` 是 registry 中的稳定 id；package 不得覆盖 `command`、`args`、`detect_command`、`install_command`、version 或 credential env allowlist。
- Lock snapshot 记录 entry id、mode、ACP command/args、exact version、descriptor digest、declared execution mode、model binding policy 与 capability matrix；不记录 binary absolute path、credential value、auth response、Docker handle 或 live readiness。
- `bora lock` 校验静态 descriptor/capability；`bora run` 在 Harness/Agent effect 前做 host 或 L1 readiness preflight。
- Model selection优先使用 `session/new` 返回的 `configOptions` 中 category=`model` 的 select option，通过标准 `session/set_config_option` 设置 exact `profile.model`。若 entry 只支持默认模型，descriptor 必须声明 `entry-default-only`，profile 只能使用锁定 sentinel `entry-default`，evidence 记录实际 current value。无匹配时 `acp_model_unavailable`，不得发 prompt。

### Process boundary: parent client vs Attempt image

```text
Parent (host Runtime)
  ParentAgentService
  AcpExecutor / typed agent-client-protocol SDK   ← Python SDK 只在这里
        │  JSON-RPC over stdio
        │  host: spawn ACP entry
        │  L1:  docker exec -u uid:gid … <acp-entry …>
        ▼
ACP entry process (codex-acp | claude-agent-acp | opencode acp | grok agent stdio)
        │  (Mode 1 may spawn/use vendor engine)
        ▼
vendor engine + auth (env projection only)
```

- Attempt 镜像 **不** 安装 `agent-client-protocol` 或 BORA parent 代码。
- L1 与 host 的 **result/event mapper 是同一 Python 模块**；container 路径不得再实现 scrape。

### L1 官方基座 BOM（Phase 4 必达）

与 [Constitution L1 BOM](../constitution/2026-08-04-acp-agent-executor-unification.md#l1-官方基座-bom必须-bake-in) 一致。实施时 `docker/attempt/install-executors.sh` + `docker/attempt/acp-entries.lock.json` 必须安装并 `command -v` 校验：

| `entry_id` | Engine package / binary（exact pin 见 local decision 6） | ACP entry package / argv | Verify（root build **与** actor UID） |
| --- | --- | --- | --- |
| `codex` | engine pin（与 registry 一致，例如 `@openai/codex@…`） | `@agentclientprotocol/codex-acp@1.1.9` → `codex-acp` | `command -v codex` ∧ `command -v codex-acp` |
| `claude-code` | engine pin（例如 `@anthropic-ai/claude-code@…`） | `@agentclientprotocol/claude-agent-acp@0.64.2` → `claude-agent-acp` | `command -v claude`（或 `claude-code`）∧ `command -v claude-agent-acp` |
| `pi` | engine pin（例如 `@earendil-works/pi-coding-agent@…`） | **`pi-acp@0.0.33`** → `pi-acp`（registry id `pi-acp`） | `command -v pi` ∧ `command -v pi-acp` |
| `opencode` | `opencode-ai@1.18.12`（或 registry 锁定等价物） | `opencode acp`（无独立 adapter 包） | `command -v opencode` 且 `opencode acp` 可启动 initialize |
| `grok-build` | n/a 或 detect `grok` | `@xai-official/grok@0.2.120` → `grok agent stdio`（全局 pin 安装，**禁止** invoke 时 `npx`） | PATH 上 `grok`（或 lock 声明的 entry argv[0]）可用 |

附加 AC：

- 二进制安装到 **全体 actor 可读** 的 PATH（默认 `/usr/local/bin`）；以 Spec 18 使用的 numeric UID 执行 verify。
- `build.py` digest 输入 = Dockerfile + `install-executors.sh` + `acp-entries.lock.json` + 相关 pin 文件。
- 官方基座预装上述 **五** entry（含 Pi Mode 1）。
- package `environment/Dockerfile` 仅 `FROM bora-attempt:l1`（或上游基座 + **同一 lock 文件** 安装），禁止自选 floating ACP 版本。

**现状差距（Current，非 Target）：** 仓库 `docker/attempt/install-executors.sh` 目前只装私有 CLI（codex/pi/opencode/claude-code），**尚未**安装 `codex-acp` / `claude-agent-acp` / **`pi-acp`** / Grok pin；OpenCode pin 亦可能落后于本 Spec。Phase 4 关闭该差距；在此之前不得声称 L1 ACP ready。

### Registry and Readiness

`bora executors -v` 的每个 ACP row 固定输出：`kind=acp`、`entry_id`、`execution_mode=acp-stdio`、`integration_mode`、`engine_command`、`acp_command/args`、exact version、`engine_ready`、`acp_entry_ready`、`readiness`。Readiness enum 只取：

| State | Meaning | Run behavior |
| --- | --- | --- |
| `ready` | engine 与 ACP entry 均通过静态 PATH/preflight | 允许进入 session protocol preflight |
| `engine-missing` | Mode 1 engine detect 缺失 | Harness 零启动，typed failure |
| `adapter-missing` | engine 已安装，Mode 1 ACP entry 缺失 | Harness 零启动；不回退 private CLI |
| `entry-missing` | Mode 2/3 ACP command 缺失 | Harness 零启动 |
| `unsupported-platform` | descriptor 无当前 platform pin | image/Attempt 零启动 |

`install_command` 只在 verbose inventory/文档展示，CLI 不执行。Readiness probe 不读取 credential value、不启动模型请求，也不把 PATH absolute hit 写入 lock。

### Visibility vs ACP permission（硬边界）

| 层 | 机制 | 默认策略 |
| --- | --- | --- |
| 物理可见 / 可写 | Provider mount、PathGrant、`docker exec -u/-w`、UID/GID/`shared_write` | 与 Spec 18 / 既有 L1 相同；gold 不 mount |
| 协议 permission | `session/request_permission` | **auto-approve**；evidence 记 outcome |
| 进程身份 | ACP entry 在 actor UID 下执行工具 | approve **不**提权为 root |
| 逻辑 cwd | `session/new.cwd` = 投影 workspace 绝对路径 | 禁止 agent 自选 host 路径扩大根 |

```text
agent tool wants path P
  → ACP permission: approved (batch default)
  → open(P) under actor UID + mount set
       ├─ P in workspace & mode allows → success
       └─ P not mounted / root-only / wrong UID → EACCES or ENOENT
```

### ACP Client Control Flow

```text
ParentAgentService reserve invocation ceiling
  → resolve locked AcpEntryDescriptor
  → launcher.spawn(host | docker exec -u actor -w workspace)
  → initialize(protocol v1; no IDE fs/terminal proxy capability)
  → session/new(cwd=projected_workspace, no MCP/additional dirs by default)
  → bind exact model through standard config option or verify entry-default-only
  → session/prompt([TextContentBlock])
      ↔ session/update → ordered evidence events
      ↔ session/request_permission → auto-approve + evidence record
      ↔ elicitation → decline (batch)
  → map stop reason + message chunks + usage to AgentResult
  → session/close when supported; close pipes; bounded terminate/kill
  → seal invocation trajectory
```

同一 BORA `AgentSession` 在当前 Attempt 内复用同一 ACP process/session 并串行多次 prompt。BORA close、cancel、deadline、worker/target failure 不使用 ACP resume/load；process/session id 不跨 Attempt。

### Result and Failure Mapping

| ACP outcome | `AgentResult` |
| --- | --- |
| `end_turn` + ordered text chunks | `ok=true`；`text` 为完整拼接；完整 JSON object 才写 `structured` |
| `max_tokens` | `ok=false`, `error=acp_stop_max_tokens`，保留 partial text/events/usage |
| `max_turn_requests` | `ok=false`, `error=acp_stop_max_turn_requests` |
| `refusal` | `ok=false`, `error=acp_stop_refusal` |
| `cancelled` | `ok=false`, `error=acp_cancelled` |
| permission request | **auto-approve**；evidence 追加 permission decision 事件；不单独因此 fail invoke |
| elicitation | decline；`ok=false`, `error=acp_elicitation_required`（batch 无人工输入） |
| tool 因 OS 权限失败（EACCES 等） | 保留 backend events；最终 `ok` 依 stop reason / 是否有可用 text；**不得**因曾 approve 而伪造文件 effect |
| auth required / model unavailable | `acp_auth_required` / `acp_model_unavailable`；prompt 零发送 |
| invalid JSON-RPC / version mismatch / unexpected EOF | `acp_protocol_error` / `acp_protocol_mismatch` / `acp_unexpected_eof` |
| timeout / target death | send cancel if possible，随后 terminate/kill；`acp_timeout` / existing target kind；partial evidence |

Agent message以外的 plan、thought、tool call、config、usage update 进入 events evidence，不参与 heuristic final-text extraction。收到未广告的 image/audio/resource block时保留 redacted event，并以 `acp_unsupported_content` 结束当前 invoke。

### Process, Security and Cleanup

- ACP stdout 专用于 JSON-RPC；任何非协议 stdout 都是 protocol error。Diagnostics 只能写 stderr，并经现有 redaction 后进入 source refs。
- Child env 只含 descriptor allowlist 与 profile locator 所解析的最小 credential。`NO_BROWSER=1` 等 non-interactive safety env 可由 descriptor 固定，不能由 package 注入 secret。
- Host launcher 使用 locked workdir；L1 launcher复用 Spec 18 actor target、UID/GID、private HOME、network 与 generation fencing。Harness 不见 process handle/ACP pipe/Docker handle。
- Cancel grace 后仍存活则 terminate→bounded wait→kill；无法确认 child/process group 停止时 writer barrier 失败，Evaluator 不启动。Cleanup warning 不覆盖已形成的 independent evaluation fact。

## Phase 0: Design authority and protocol/pin closure

### Goal

先把 canonical profile、ACP ownership、method subset、permission/structured policy、entry pins 与 host/L1 placement 写入设计权威和未完成 Roadmap outcome，并用最便宜的真实 upstream/host probe验证四个高风险前提。

### Tasks

- 将 Constitution status/history 与用户批准同步；若用户不接受任一 local decision，先改本 Spec/Constitution，再继续。
- 将 Constitution status/history 与用户批准同步；若用户不接受任一 local decision，先改本 Spec/Constitution，再继续。
- 同步 design/02 profile 与 L1 基座 BOM、design/05 §8.4.3a ACP inlet、design/06 adapter admission、ARCHITECTURE Target/Current、ROADMAP 未勾 `v0.19`、AGENTS 边界（**draft 文档已预写 Target；B1 批准后 Phase 0 只复核与 probe，不再从零起草**）。
- 用 official ACP registry protocol matrix、exact npm/PyPI metadata 与本机 `--version`/initialize/session probe 验证 pins、protocol v1、model config、permission/auth 行为；不发送有副作用 prompt。
- 若 R1/R2/R3 任一机制不成立，停止依赖实现，记录 `BLOCKED.md` 并将未决机制转 Research；不得用 private parser fixture 替代。

### Files

- `specs/constitution/2026-08-04-acp-agent-executor-unification.md`
- `specs/active/19-acp-agent-executor-plan.md`
- `docs/design/02-task-package-and-config.md`
- `docs/design/05-runtime-core.md`
- `docs/design/06-capability-adapter-visibility.md`
- `ARCHITECTURE.md`
- `specs/ROADMAP.md`
- `AGENTS.md`

### Acceptance Criteria

#### Success

- [x] Design 精确冻结 `executor: acp` + `options.entry`、one-client/two-launcher、L1 BOM bake-in、parent client 边界、method subset、permission/structured/model policy、pins、outlet 与 authority（draft 已写入；用户批准后勾 Phase 0 完成）。
- [ ] Official registry/host probe 对 Codex、Claude、OpenCode、Grok 记录 initialize/session readiness、protocol version、auth/model/permission 观察；未发送外部 Agent effect。
- [x] Roadmap 仅有未勾选 `v0.19` planning entry，无 Version Index 完成勾选、无关键交付完成态。

#### Expected failure

- [ ] 设计明确拒绝 unknown/floating entry、runtime install、private/host fallback、ACP-as-Capability、ACP end_turn→PASS；任一冲突使 strict validation/docs review 失败。
- [ ] Grok `0.2.120` 或任一 pin 无法完成最低 protocol probe 时 Phase 0 保持 open，后续 Phase 不开始。

#### Gates

- [ ] `uv run bora executors -v` baseline 已保存到 implementation evidence 摘要。
- [ ] `python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict` 与 `git diff --check` 通过。
- [ ] Phase 0 后刷新 Decision Summary、R1–R3 与 Planning gate；不修改 production source。

## Phase 1: ACP registry, lock snapshot and inventory

### Goal

建立单一静态 entry registry 与可审计 lock/readiness 表面，先让操作者准确区分 engine missing、Mode 1 adapter missing 与 ACP entry ready，不启动模型请求。

### Tasks

- 创建 schema-validated `acp_entries.json` 和 typed loader；登记四个最低 entry、mode、command/args、detect/install、pins、credential allowlist、model binding 与 platform support。
- `ExecutionMode` 增加 `acp-stdio`；`executor: acp` capability 与 entry-specific capability 分层（`options.entry: pi` 走 Mode 1）；`openai-http` 保持 `api-client`；私有 `executor: pi` 仅 migration tombstone。
- Config validation 强制 `options.entry`、禁止 package command/version override，并把 descriptor snapshot/digest 写入 lock。
- 扩展 inventory/CLI 输出 exact readiness enum；probe 只检查 command/version/protocol preflight所需静态条件，不读取或输出 secret。
- 添加 duplicate/unknown/malformed descriptor、unknown entry、adapter-missing、no-auto-install、lock-no-secret tests。

### Files

- `src/bora/adapters/acp_entries.json`
- `src/bora/adapters/acp_registry.py`
- `src/bora/adapters/executor_capabilities.py`
- `src/bora/adapters/executor_inventory.py`
- `src/bora/config/load_and_lock.py`
- `src/bora/application/run_command.py`
- `src/bora/cli/main.py`
- `tests/adapters/test_acp_registry.py`
- `tests/adapters/test_executor_inventory.py`
- `tests/config/test_acp_profile.py`
- `tests/acceptance/test_executors_cli.py`
- `tests/security/test_acp_lock_no_secret.py`

### Acceptance Criteria

#### Success

- [ ] `uv run bora executors -v` 输出四个 ACP entry 的 mode/command/pin/readiness；Mode 1 同时显示 engine 与 adapter readiness。
- [ ] 合法 ACP profile lock 包含 descriptor digest、entry version、model policy 与 `execution_mode=acp-stdio`，不依赖当前 PATH absolute location。

#### Expected failure

- [ ] Unknown/duplicate entry、缺 `options.entry`、package-supplied command/version/install、descriptor pin mismatch 在 lock 前 fail closed。
- [ ] 可控 PATH probe 中 engine present + adapter absent 只得到 `adapter-missing`；`bora run` preflight 非零且 install/private fallback counter 均为零。

#### Gates

- [ ] `uv run pytest tests/adapters/test_acp_registry.py tests/adapters/test_executor_inventory.py tests/config/test_acp_profile.py tests/acceptance/test_executors_cli.py tests/security/test_acp_lock_no_secret.py -q` 通过。
- [ ] `uv run ruff check src/bora/adapters src/bora/config src/bora/application tests/adapters tests/config tests/acceptance/test_executors_cli.py` 与 `uv run pyright` 通过。
- [ ] Phase/child checkboxes与 Decision Summary 同步；未创建 ACP invoke client。

## Phase 2: Single ACP client MVP with Mode 2 OpenCode

### Goal

以 OpenCode native `opencode acp` 证明一个 typed stdio client 能完成 BORA session multi-invoke、统一 event/result/evidence、cancel/cleanup 与独立 evaluation。

### Tasks

- exact pin `agent-client-protocol==0.12.0`，创建稳定 `AgentResult`/`AgentExecutor` contract，保留临时 import alias 到 Phase 5。
- 实现唯一 `AcpExecutor`/client session：spawn streams、initialize、new/model bind、prompt/update、**permission auto-approve**、elicitation decline、cancel/close、timeout/kill、result mapping。
- 将 ParentAgentService 的 BORA session 绑定到 ACP process/session；同 session prompts 串行，不使用 load/resume，不跨 Attempt。
- 将 ACP update/stop/usage/permission decision/agent info/entry metadata 送入现有 trajectory store；全路径 redaction，stdout protocol-only，stderr diagnostic-only。
- 创建 deterministic ACP fixture servers 覆盖 echo/multi-turn、malformed、unexpected EOF、permission-approved、unsupported content、hang/cancel；fixture 不代替真实 OpenCode public smoke。
- 安全/隔离属性测：approve 后对 root 私有路径或未 mount 路径 tool 仍失败（EACCES/ENOENT），无伪写成功。
- 创建 `examples/core/acp-agent-conformance`，Phase 2 先启用 `opencode-acp` profile；Harness 不读取 entry/executor name。

### Files

- `pyproject.toml`
- `uv.lock`
- `src/bora/adapters/agent_contract.py`
- `src/bora/adapters/agent_acp.py`
- `src/bora/adapters/agent_registry.py`
- `src/bora/runtime/agent_service.py`
- `src/bora/evidence/store.py`
- `tests/fixtures/acp/echo_agent.py`
- `tests/fixtures/acp/failure_agent.py`
- `tests/adapters/test_agent_acp.py`
- `tests/runtime/test_agent_service_acp.py`
- `tests/security/test_acp_no_secret.py`
- `tests/acceptance/test_acp_agent_conformance.py`
- `examples/core/acp-agent-conformance/bora.yaml`
- `examples/core/acp-agent-conformance/harness.py`
- `examples/core/acp-agent-conformance/evaluator.py`
- `examples/core/acp-agent-conformance/README.md`

### Acceptance Criteria

#### Success

- [ ] Official SDK fixture 完成 initialize→new→exact model→两次 prompt→close；两次 invocation 共享 ACP session但拥有不同 BORA invocation id/evidence directory。
- [ ] 真实 `opencode acp` public command返回 independent evaluator PASS；metadata 为 `executor_kind=acp`、`acp_entry_id=opencode`、protocol v1 与 exact entry version。
- [ ] `AgentResult.text/structured/usage/events` 只由标准 typed ACP messages生成，完整 JSON object `{"answer": 42}` 通过 validated-text。

#### Expected failure

- [ ] Malformed stdout、version mismatch、unexpected EOF、elicitation、image/audio/resource、non-object final text、timeout/cancel 各映射到冻结 error kind并保留 partial evidence，无伪 final response/PASS。
- [ ] Permission request 被 auto-approve 且写入 evidence；**不**因此单独 fail invoke。
- [ ] `{"answer": 42}` 周围出现 prose 或嵌套文本片段时 `structured=None`；禁止 regex/last-object salvage。

#### Gates

- [ ] `uv sync --frozen`、`uv run pytest tests/adapters/test_agent_acp.py tests/runtime/test_agent_service_acp.py tests/security/test_acp_no_secret.py tests/acceptance/test_acp_agent_conformance.py -q` 通过。
- [ ] `uv run ruff check .`、`uv run pyright`、strict Specs validator 与 `git diff --check` 通过。
- [ ] 真实 OpenCode smoke与全 evidence secret scan 通过；fixture-only green 不得关闭 Phase 2。

## Phase 3: Mode 1 Codex/Claude/Pi and Mode 3 Grok Build

### Goal

让 Codex/Claude/**Pi** standalone adapters 与 Grok vendor entry 复用 Phase 2 client，在 host public path 形成 **五** entry conformance；vendor 差异只留 registry row/外部 process。

### Tasks

- 实现 descriptor-driven auth/model/non-interactive env preflight；禁止 browser login 与 vendor field branch；permission 遵循默认 auto-approve（见 decision 4）。
- 为 Codex/Claude/**Pi** 区分 engine present 与 adapter present（`pi-acp`）；为 Grok 使用已安装 exact `grok agent stdio`，不在 invoke 时执行 `npx latest`。
- 扩展 conformance package **五个**冻结 profile（含 `pi-acp`），逐个运行真实 prompt/evaluator/evidence/secret scan。
- 验证同一 Harness/profile-only switch；新增 Mode 1 adapter-missing（含仅有 `pi` 无 `pi-acp`）、auth-required、model-unavailable、Grok pin mismatch failures。
- 记录 entry 实际 agent info/protocol/model/stop reason；不把 account availability写成 repository-owned prerequisite。

### Files

- `src/bora/adapters/acp_entries.json`
- `src/bora/adapters/acp_registry.py`
- `src/bora/adapters/agent_acp.py`
- `src/bora/adapters/child_env.py`
- `tests/executors/test_acp_mode_feasibility.py`
- `tests/acceptance/test_acp_agent_conformance.py`
- `tests/acceptance/test_acp_public_failures.py`
- `tests/security/test_acp_entry_credentials.py`
- `examples/core/acp-agent-conformance/bora.yaml`
- `examples/core/acp-agent-conformance/README.md`

### Acceptance Criteria

#### Success

- [ ] **五**条 host success commands 均通过真实 ACP entry、同一 `AcpExecutor` class、同一 result mapper 与独立 evaluator；Harness 源码无 entry/vendor branch。
- [ ] Codex/Claude/**Pi** inventory 分别证明 engine/adapter 双 readiness；Grok invocation command不含无版本 `npx`，entry/pin 与 evidence 一致。

#### Expected failure

- [ ] Engine missing、adapter missing、auth required、model unavailable、pin mismatch 各在 prompt前或当前 invoke boundary typed fail，无其它 executor/private parser/host fallback effect。
- [ ] 任一 entry 只能靠 parent 代持 host fs、interactive human UI 或 floating install 才能成功时，本 Phase 保持 open并路由 Research，不降低「工具在 actor 投影内执行」policy。

#### Gates

- [ ] `uv run pytest tests/executors/test_acp_mode_feasibility.py tests/acceptance/test_acp_agent_conformance.py tests/acceptance/test_acp_public_failures.py tests/security/test_acp_entry_credentials.py -q` 通过。
- [ ] 四个 real host smoke各记录 command、entry/pin、Result、logs locator与 secret scan；缺 credentials 可跳本地开发，但不能关闭 Spec acceptance。
- [ ] Ruff、Pyright、focused/full pytest、strict validator 与 `git diff --check` 通过。

## Phase 4: Docker L1 placement and parity

### Goal

在 repository-owned L1 官方基座 **bake-in** 最低 **五** entry 的 engine + ACP 入口（exact pin，含 `pi`+`pi-acp`），由 `docker exec` launcher 把 **parent 侧同一 typed client** 接到 actor-bound ACP entry process，证明 host/container 无第二 parser、无 host fallback、numeric UID 下 PATH 可用。

### Tasks

- 引入 `docker/attempt/acp-entries.lock.json`，与 `src/bora/adapters/acp_entries.json` pin 同源；改写 `install-executors.sh`：**安装 Mode 1 engine+adapter（含 `pi`+`pi-acp`）、Mode 2 OpenCode、Mode 3 Grok pin**（见上文 BOM 表）。
- `build.py` digest 覆盖 Dockerfile、`install-executors.sh`、`acp-entries.lock.json`；禁止只 digest Dockerfile；禁止 image 内 `npx` 无版本安装。
- Image build 后以 root 与 **numeric actor UID** 分别 `command -v` / 最小 `--help` 校验 **五** entry；Mode 1 缺 adapter 使 build 或 preflight 失败。
- 将 `agent_container.py` 收窄为 `AcpProcessLauncher`/target placement（stdio attach），删除 ACP-capable vendor `_cli_argv`、`_try_parse_structured` 与 JSON regex；client/result mapper 只在 parent `agent_acp.py`。
- `run_l1.py` 为 locked ACP profile 构造 launcher 并复用 ParentAgentService；保留 actor UID/GID/private HOME/generation/no-host-fallback。
- 创建 L1 public package：至少两次 SDK invoke + independent evaluator；另加 **静态** image inventory gate（**五** entry PATH，不强制五次真实模型调用）。
- 覆盖 entry missing、dead target、cancel/timeout、residual writer；secret/gold/handle scan。

### Files

- `docker/attempt/acp-entries.lock.json`
- `docker/attempt/Dockerfile`
- `docker/attempt/install-executors.sh`
- `docker/attempt/build.py`
- `src/bora/adapters/agent_acp.py`
- `src/bora/adapters/agent_container.py`
- `src/bora/application/run_l1.py`
- `src/bora/adapters/provider_docker.py`
- `tests/provider_l1/test_acp_container_placement.py`
- `tests/provider_l1/test_acp_image_bom.py`
- `tests/acceptance/test_l1_acp_agent.py`
- `tests/security/test_acp_l1_projection.py`
- `tests/architecture/test_acp_pin_parity.py`
- `examples/l1/acp-agent-placement/bora.yaml`
- `examples/l1/acp-agent-placement/harness.py`
- `examples/l1/acp-agent-placement/evaluator.py`
- `examples/l1/acp-agent-placement/environment/Dockerfile`
- `examples/l1/acp-agent-placement/README.md`

### Acceptance Criteria

#### Success

- [ ] `uv run python docker/attempt/build.py --platform linux/arm64` 生成 image lock：含 engine/entry exact versions 与完整 build-input digest；BOM **五** entry 在镜像内 PATH 可 `command -v`（actor UID）。
- [ ] Mode 1 镜像内 `codex`∧`codex-acp`、`claude`∧`claude-agent-acp`、`pi`∧`pi-acp` 同时存在；Grok 为 pin 安装而非 `npx` 包装脚本依赖网络。
- [ ] L1 public success 完成至少两次 SDK invoke（Codex 或 OpenCode 至少一个真实 entry），metadata/evidence 与 host path 同 schema，`execution_location=attempt-container`、numeric non-root、private HOME、`host_fallback_count=0`。
- [ ] Host 与 container 注入同一 ACP update sequence，normalized `AgentResult`/events 字节等价（placement metadata 除外）；mapper 源文件仅 `agent_acp.py`。

#### Expected failure

- [ ] Container engine/adapter missing、target dead/generation mismatch、credential missing、protocol EOF、timeout/cancel/residual writer 各 typed fail；private parser 与 host effect counters 均为零。
- [ ] 无法确认 ACP child/process group 停止时 evaluator 不启动；partial trajectory 可定位，cleanup warning 不伪造 score。

#### Gates

- [ ] `uv run pytest tests/provider_l1/test_acp_container_placement.py tests/provider_l1/test_acp_image_bom.py tests/acceptance/test_l1_acp_agent.py tests/security/test_acp_l1_projection.py tests/architecture/test_acp_pin_parity.py -q` 通过。
- [ ] Real Docker/Agent success 与 negative matrix、image pin/digest、secret/gold/handle scans 通过。
- [ ] L0 ACP、Spec 18 L1 SDK/multi-agent、Ruff、Pyright、full pytest、strict validator 与 `git diff --check` 通过。

## Phase 5: Migration, private scrape deprecation and status sync

### Goal

迁移仓库内 ACP-capable profiles与回归 journey，删除 Codex/OpenCode/Claude 和 container generic private scrape，使新增 ACP entry只需 registry row；同步文档状态但不越权勾选 Roadmap Version Index。

### Tasks

- 将 `AgentResult`/protocol imports统一到 `agent_contract.py`；删除 `agent_codex.py`、`agent_opencode.py`、`agent_claude_code.py`、`agent_pi.py` 的 private parser/factory，或保留仅能给出明确 migration error 的无 parser tombstone。
- 删除 `agent_container._cli_argv` 对 ACP entries 的 vendor dispatch、`_try_parse_structured`、`_extract_json_object` 与 regex；L1 ACP只走 common launcher/client。
- 迁移所有当前 `executor: codex|opencode|claude-code|pi` example/test profile 到 canonical `executor: acp` + `options.entry`（`pi` → `entry: pi`）；`openai-http` 保持 `api-client`。
- 添加 architecture gate：ACP client实现数量为一，ACP modules中无 vendor stdout field guessing，host/L1 mapper identity相同；新增 entry fixture只改 registry row。
- 回归 v0.13–v0.18 public paths、evaluator negative、hard ceiling、trajectory export、L1 multi-agent；原 Pi private-CLI 旅程改为 ACP entry 或诚实 migration error。
- 同步 README、examples index、Skills、Architecture Current、design implementation note、本 Spec evidence；Roadmap v0.19 child acceptance只按真实证据同步，Independent review保持 off时 Version Index不勾。

### Files

- `src/bora/adapters/agent_contract.py`
- `src/bora/adapters/agent_acp.py`
- `src/bora/adapters/agent_registry.py`
- `src/bora/adapters/executor_capabilities.py`
- `src/bora/adapters/executor_inventory.py`
- `src/bora/adapters/agent_codex.py`
- `src/bora/adapters/agent_opencode.py`
- `src/bora/adapters/agent_claude_code.py`
- `src/bora/adapters/agent_pi.py`
- `src/bora/adapters/agent_container.py`
- `src/bora/adapters/agent_openai_http.py`
- `src/bora/application/run_l1.py`
- `tests/architecture/test_no_acp_private_scrape.py`
- `tests/runtime/test_trajectory_source_probe.py`
- `tests/acceptance/test_builtin_executor_conformance.py`
- `tests/acceptance/test_l1_multi_agent_scheduling.py`
- `examples/core/agent-eval/bora.yaml`
- `examples/core/attempt-trajectory/bora.yaml`
- `examples/core/builtin-executor-conformance/bora.yaml`
- `examples/core/builtin-executor-mixed/bora.yaml`
- `examples/core/hard-ceiling-trajectory/bora.yaml`
- `examples/core/orchestration-environment/bora.yaml`
- `examples/core/sdk-agent-session/bora.yaml`
- `examples/journeys/multiagent-env-min/bora.yaml`
- `examples/journeys/tau2-dialog-min/bora.yaml`
- `examples/journeys/terminal-jsonl-agg/bora.yaml`
- `examples/l1/builtin-executor-visibility/bora.yaml`
- `examples/l1/multi-agent-container-per-group/bora.yaml`
- `examples/l1/multi-agent-shared-container/bora.yaml`
- `examples/l1/provider-l1-agent-eval/bora.yaml`
- `examples/l1/sdk-session-single-actor/bora.yaml`
- `README.md`
- `examples/README.md`
- `ARCHITECTURE.md`
- `docs/design/05-runtime-core.md`
- `specs/ROADMAP.md`
- `skills/bora-platform/SKILL.md`
- `skills/bora-config-package/SKILL.md`
- `specs/active/19-acp-agent-executor-plan.md`

### Acceptance Criteria

#### Success

- [ ] Codex、Claude、**Pi**、OpenCode、Grok 的 public profiles 只走 `executor: acp`；新增测试 entry只增加 registry row和 fixture metadata，不新增 parser/client class。
- [ ] `openai-http` 行为与 regressions 保持；旧 `executor: pi` 给出 migration error 或已全部迁到 `entry: pi`。
- [ ] 所有受影响 public journey仍通过 independent evaluator，trajectory/result/cleanup事实分离，证据等级只描述实测 entry/pin/platform。

#### Expected failure

- [ ] 旧 `executor: codex|opencode|claude-code` config给出 stable migration error并在 Agent effect前失败；不存在 alias/private fallback。
- [ ] Architecture test发现第二 ACP client、vendor field guess、regex JSON scrape、container result mapper或无 pin install时失败。

#### Gates

- [ ] `uv run pytest tests/architecture/test_no_acp_private_scrape.py tests/runtime/test_trajectory_source_probe.py tests/acceptance/test_builtin_executor_conformance.py tests/acceptance/test_l1_multi_agent_scheduling.py -q` 通过。
- [ ] 五 entry host smokes、L1 ACP smoke、expected-failure matrix 与所有 affected regressions通过。
- [ ] Frozen install、Ruff、Pyright、full pytest、strict Specs validator、relative-link checks、Skills consistency与 `git diff --check` 通过。
- [ ] Spec Phase/AC/gates、Decision Summary、docs/Architecture/README/Skills/Roadmap child state同批回写；不因本 Spec planning或 review-off直接勾 Roadmap Version Index。

## Completion Gates

以下 gate 全部通过后才可把本 Spec 标为 completed；env-gated real Agent smoke缺任一实际成功记录时保持 in-progress：

```bash
uv sync --frozen
uv run ruff check .
uv run pyright
uv run pytest -q
uv run pytest tests/architecture/test_no_acp_private_scrape.py -q
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
git diff --check
```

- [ ] Host real success：Codex、Claude Code、**Pi**、OpenCode、Grok Build 各一次，entry/pin/model/Result/logs可核对。
- [ ] L1 real success：image BOM **五** entry PATH（actor UID，含 `pi-acp`）+ 至少 Codex/OpenCode/Pi 之一 multi-invoke；host fallback 为零；Python ACP SDK 不在 attempt image。
- [ ] Expected failures：adapter/engine missing、auth/model/protocol/timeout/target/writer 全部 fail closed；越权路径在 approve 后仍 OS-denied。
- [ ] Regression：Spec 13–18受影响 smokes、Pi residual、`openai-http`、evaluator negative与trajectory export通过。
- [ ] Security：lock、stdout/stderr、workspace、image history与全 evidence credential sentinel扫描零命中。
- [ ] Documentation：design、Architecture、Roadmap child acceptance、README/examples/Skills与实际行为同步；无未实现 ACP capability claim。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 用 official SDK 仍在各 entry 写 vendor branch | client只读 typed ACP schema；entry差异限于 descriptor row与外部 process，architecture test扫描 vendor/private字段 |
| `executor: acp` 隐藏实际 backend与版本 | lock/evidence强制 entry id、exact version、descriptor digest、agent info、model与execution location |
| Mode 1 engine present被误报 ready | inventory独立 `engine_ready`/`acp_entry_ready`；`adapter-missing` public negative |
| Runtime auto-install或 floating `npx`破坏复现 | install command documentation-only；host显式供应；L1 build exact pin并记录digest |
| 误以为 ACP approve = root / 突破 mount | 文档+测试：approve 后 EACCES/ENOENT；工具在 actor UID 下执行；不广告 parent 代持 fs |
| Permission 无审计 | 每次 auto-approve 写入 evidence permission decision 事件 |
| ACP output又退化为 JSON猜测 | 只接受完整final text JSON object；prose/substring/reverse-scan negatives |
| L1借placement重写第二 client | launcher只供应streams/process；host/container mapper identity和source scan作gate |
| ACP session id污染Core identity或跨Attempt复用 | ParentAgentService保持BORA session/Attempt binding；ACP id私有、Attempt teardown即销毁 |
| trajectory/end_turn被误作PASS | AgentResult/evidence/evaluator facts继续分离；evaluator negative regression必跑 |
| 混淆 `pi-acp` 与 `pi-shell-acp` | registry 只登记 client→pi 的 `pi-acp`；文档与 pin 表禁止反向桥 |
| 仅装 `pi` 未装 `pi-acp` 却标 ready | Mode 1 readiness 要求 engine∧adapter；adapter-missing public negative |

## User Acceptance

- [x] 用户批准 Constitution 与本 Spec local decisions 1–8（会话确认 2026-08-04：entry 形态、Pi 纳入、L1 bake-in、permission auto-approve + OS 边界）。
- [x] 用户授权按本 Spec 推进 production 实施（同一会话；非「仅文档」）。
- [ ] Spec 整包 acceptance（Phase 0–5 证据齐）— 实现后勾选，**不**再要求新的产品决策。


## Evidence (implementation progress)

| Smoke | Result |
| --- | --- |
| Host `opencode-acp` | PASS |
| Host `codex-acp` | PASS |
| Host `pi-acp` | PASS |
| Host `claude-acp` | PASS |
| Host `grok-build-acp` | PASS |
| L1 `examples/l1/acp-agent-placement` | PASS, `assurance:l1`, `execution_location=attempt-container`, `host_fallback_count=0` |
| Image BOM actor UID PATH | codex, codex-acp, pi, pi-acp, opencode, claude, claude-agent-acp, grok |
| Inventory five ACP entries | all `ready` on implementer host after pin install |

**Not claimed:** Roadmap `v0.19` Version Index; suite-wide `isolated`; Phase 5 private scrape removal complete.
