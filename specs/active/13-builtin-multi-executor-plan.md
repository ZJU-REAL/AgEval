# Spec 13 — 内置多 Executor 与 multi-profile 边界

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.14`；`pi` / `opencode` 必需 built-in Adapter、`claude-code` 可选 residual、capability matrix、credential projection、multi-profile trajectory |
| Type | feat |
| Priority | P0 |
| Status | completed |
| Planning gate | closed |
| Completed | 2026-08-03 |
| Independent review | required |
| Dependencies | [Spec 12](12-attempt-evidence-trajectory-plan.md) 完成；[Roadmap v0.13](../ROADMAP.md#v013--attempt-evidence-与-agent-轨迹落盘) 勾选 |
| Decisions | [Roadmap v0.14](../ROADMAP.md#v014--内置多-executor-与-multi-profile-边界)、[配置切换与混用](../../docs/design/05-runtime-core.md#842-配置如何表达切换与混用)、[归一化 invoke 契约](../../docs/design/05-runtime-core.md#844-归一化-invoke-契约跨后端) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: Spec 13 closed; proceed to Spec 14 / v0.15 Docker L1 visibility.

### Current blockers

- None.

### Potential blockers

- None.

## Phases

- [x] Phase 0: 必需三后端真实 feasibility、credential locator 与 capability matrix 冻结
- [x] Phase 1 (14a，可选 residual): `claude-code` Adapter 与 lock validation
- [x] Phase 2 (14b): `pi` Adapter + Zhipu-compatible env projection + trajectory
- [x] Phase 3 (14c): `opencode` Adapter + mixed-profile isolation
- [x] Phase 4: three-backend public conformance、可选 `claude-code` probe、安全回归与状态同步

## Background

### Problem

同一套 Harness 业务代码，想换 Agent 后端（Codex / pi / OpenCode…）做对比时，今天要么写死一种后端，要么在 harness 里 `if executor == ...` 分支。  
那样实验不可比：边界、密钥、轨迹、失败语义各走各的。需要的是：**Harness 只写 profile 名**；换后端只改配置；Runtime 统一管调用、密钥和落盘。

### Current Behavior

- 生产路径主要是 `codex`；仓库里另有 HTTP/registry 切片，**不等于** pi/OpenCode 已验收。
- 2026-08-03 宿主观察（不记密钥值）：PATH 上有 `pi`、`opencode`、`codex`；没有 `claude`/`claude-code`。路径只作本机备忘，不写进 lock。
- `.env` 里目前只观察到键名 `zhipu_coding_api_key`（未读值）。Phase 0 再根据 CLI 帮助冻结真正要用的变量名。

### Goals and Non-goals

- Goal: **主仓内置**至少 `codex`、`pi`、`opencode` 三种后端；本机有 `claude-code` 再加，没有就写 residual，不挡版本验收。
- Goal: API Key 等只从用户 `.env`/CI 注入到**该后端进程**；缺 key 时在真正发请求前失败，不静默换后端。
- Goal: 同一次 Attempt 里两个 profile 各有自己的会话、调用编号、次数统计和轨迹目录，互不覆盖。
- Non-goal: 不做「装个 wheel 自动发现插件」的市场；本阶段固定名单注册。
- Non-goal: 第三方 Agent SDK 不能自己定 Attempt id、密钥库、次数上限或 PASS。
- Evidence boundary: `codex`/`pi`/`opencode` 各至少一次真实调用 + 独立评测 + 轨迹；`claude-code` 没有就诚实 residual。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora run <package> --task <task-id>`。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: Spec 12 Codex multi-invoke trajectory success/redaction/failure。
- Observable result: 一种后端能经 Agent Service 落盘。

### User Story

作为 Harness 作者，我只改 `bora.yaml` 里的 profile（或加第二个 profile），**不改 harness 业务代码**，就能换用 Codex / pi / OpenCode；每次调用仍按 v0.13 规矩落盘，缺密钥就明确失败，不会偷偷退回另一种后端。

### Scope Boundary

- Included: fixed built-in registry、profile/capability lock、14b `pi`、14c `opencode`、可用时的 14a `claude-code` residual、credential projection、single/mixed profile E2E、trajectory conformance。
- Deferred to `v0.15`: CLI executor 容器化、network/path projection 全收口。
- Deferred to `v0.19+`: entry-point plugins、第三方 package 分发、VM 和远程 workers。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| v0.13 trajectory store | `baseline-verified` | Spec 12 | 运行 v0.13 public gates | Codex success/failure/redaction 都可解析 | 清理本次 run-owned temp evidence |
| `pi` / `opencode` host CLI | `external-accepted` | User-owned installation；2026-08-03 观察为 `/opt/homebrew/bin/pi` 与 `/opt/homebrew/bin/opencode` | Phase 0 用 `command -v`、`--version`、`--help` 和 non-mutating preflight；不自动升级，不把绝对路径写入生产合同 | 冻结 executable/version/non-interactive/event/session/exit semantics | 不改全局配置；终止本次 child/session |
| API credential value | `external-accepted` | User-owned `.env` / CI secret store；当前仅观察键名 `zhipu_coding_api_key` | 使用 `uv run --env-file .env ...`；Phase 0 从 CLI help + 实际 `.env` 键冻结后端原生名，再映射到 Runtime logical locator | preflight 只检查已冻结 locator 存在与 scoped API 成功，不输出值；不自动别名或盲猜大写变体 | `.env` 保持 gitignored/untracked；child 退出后丢弃 projection |
| Built-in adapters/matrix | `phase-produced` | Agent / Phase 0–3 | 必需实现 14b/14c；14a 仅在 `claude-code` 可用时实现；每段先 real probe 再接 production | three-backend conformance + 真实 invoke + trajectory + sentinel scan；可选 14a 单独记录 | 回收 child/session/temp config；不删 host config/account |
| Mechanism conformance package | `phase-produced` | Agent / Phase 2–4；`examples/core/builtin-executor-conformance/` | 创建同一 Harness/profile-only package 与 credential/capability/session failure tasks | `codex`、`pi`、`opencode` success + mixed-profile + expected failures 经 production CLI 通过 | 只清理该 run 的 evidence/workspace/child；tracked package 保留 |

</details>

`.env` 只在实施期作宿主 locator 值容器，不被 `git add`、复制、记录或扫描输出。Phase 0 必须从 CLI help + 实际 `.env` 键冻结每个后端的最小原生 env 名集，再建立 Runtime logical locator 映射；当前只能把 `zhipu_coding_api_key` 记为 host observation。`claude-code` 不是最低成功路径前置；不可用时保持 14a residual。

### Runnable Acceptance

- Success smoke: 同一 `examples/core/builtin-executor-conformance` Harness 仅通过 `bora.yaml` profile 切换完成 `codex`、`pi`、`opencode` 真实 invoke；可用时另验 `claude-code` residual。
- Expected failure: unknown kind、missing locator、capability mismatch、cross-Attempt session 均在外部调用前 typed fail。
- Regression smokes: v0.13 Codex trajectory、evaluator negative、现有 invocation-limit behavior 与 L1 secret tests；完整 production hard-ceiling closure 仍属于 Spec 16 / v0.17。
- Observable evidence: lock capability snapshot、per-profile trajectory trees、backend conformance record、credential scans。

### Extension Seams

- `AgentExecutor`: 必需三个 built-in 与可选 `claude-code` 共用薄合同；本版 registry 是固定 composition，不扩展为动态发现。
- `ExecutorCapabilities`: lock 携带可比较的 declared/effective 能力，backend-specific 原始信息留在 Adapter evidence。

## Design

> Inherited design: [Agent Service](../../docs/design/05-runtime-core.md#843-agent-serviceruntime)、[归一化 invoke](../../docs/design/05-runtime-core.md#844-归一化-invoke-契约跨后端)、[热路径](../../docs/design/05-runtime-core.md#845-热路径与限制)、[轨迹所有权](../../docs/design/05-runtime-core.md#895-所有权与非目标)
>
> Local delta: 暂不使用设计中的 entry-point 发现，以主仓固定 registry 交付 `codex`、`pi`、`opencode` 最低闭环，`claude-code` 作可选 residual；长期扩展契约未被删除。

### Locked Capability Matrix

| Field | Rule |
| --- | --- |
| `tools` | `native` / `adapter-loop` / `unsupported`；task 要求不满足时 Attempt 前拒绝 |
| `structured_output` | `native` / `validated-text` / `unsupported`；降级模式必须显式进 lock |
| `session` | `new-only` / `resume-within-attempt` / `unsupported`；handle 绑 Attempt + profile + executor |
| `stream` | `native-events` / `synthetic-lifecycle`；两者都必须满足 §8.9 |
| `execution_mode` | `cli-process` / `api-client`；v0.15 依此决定 container/location 证据 |

### Failure Semantics

- registry/capability/locator 校验在 Attempt 或 invoke 之前失败，不用另一 executor 兜底。
- child/API 已启动后失败则保留 backend kind、profile、typed error 和 partial trajectory，不改写 evaluator truth。
- env projection 采用显式 allowlist，不传递整个 host environment；value/path 均不序列化。

## Phase 0: 真实 feasibility 与 capability matrix 冻结

### Goal

用 host-installed CLI 和用户接受的 `.env` 能力证明 `codex`、`pi`、`opencode` 的真实 invocation/event/session/termination 机制；同时检查 `claude-code` 可用性，缺失时冻结 residual，再开始必需 Adapter。

### Tasks

- 记录 executable/version/non-interactive command、输出模式、exit/cancel、session artifact 和 required locator names，不记录值。
- 对 tools/structured/session/stream/execution mode 做属性 probe，冻结 declared/effective matrix 和 fail-closed 规则。
- 使用 `uv run --env-file .env ...` 传入宿主值，验证跟踪状态与 evidence 零 secret 命中。

### Files

- `src/bora/runtime/agent_service.py`
- `src/bora/adapters/agent_registry.py`
- `tests/executors/test_builtin_feasibility.py`
- `tests/executors/test_capability_matrix.py`
- `tests/security/test_executor_env_projection.py`

### Acceptance Criteria

- [x] `codex`、`pi`、`opencode` 的真实版本、命令、locator 名、能力和失败语义均有可重复 probe，无假设字段；`claude-code` 记录 available 或 residual。
- [x] `pi`/`opencode` 可使用 host-installed 实体和 Zhipu-compatible provider 完成最小 invoke；不可用时将机制缺口路由 Research。
- [x] 全部 probe 不改全局 config、不打印 env 值、不跟踪 `.env`，sentinel scan 通过。
- [x] `R1` 与 `R3` 关闭后才进入必需 14b/14c；`R2` 以 available 或显式 residual 关闭。

## Phase 1 (14a，可选 residual): `claude-code` 与 lock validation

### Goal

若 Phase 0 确认 executable/account 可用，则交付 `claude-code` Adapter；若不可用，将 14a 保持为有证据 residual，不阻塞必需三后端路径。

### Tasks

- 若 executable/account 可用，实现 `claude-code` process Adapter、credential allowlist、event/result normalization 和 trajectory，并将它的 effective capability 写入 lock。
- 若不可用，记录 executable/account probe 与 residual 边界，不下载 CLI、不伪造 Adapter success、不阻塞 Phase 2–4。

### Files

- `src/bora/adapters/agent_claude_code.py`
- `tests/executors/test_claude_code_executor.py`

### Acceptance Criteria

- [x] `claude-code` 可用时，真实 invoke 产生归一化 result、独立 trajectory 和 evaluator result；不可用时，Phase 0 记录 executable/account residual 且 Version Index 不宣称该后端。
- [x] 可用或 residual 两条分支均不改变必需三后端的 lock/registry 契约，focused gates 通过。

## Phase 2 (14b): `pi` Adapter

### Goal

使用 Phase 0 冻结的 host CLI/provider 机制交付 `pi`，保持同一 lock/trajectory/credential 合同。

### Tasks

- 收口 `codex`、`pi`、`opencode` 与可选 `claude-code` 的 fixed composition，拒绝 unknown/duplicate/dynamic entry point。
- 将 profile resolution、executor version 和 effective capability matrix 写入 lock digest；unknown kind/capability mismatch 在 Attempt 零启动时 typed fail。
- 实现 process/API bridge、最小 env allowlist、event/session/result normalization 和 cancel/timeout。
- 执行 missing locator、capability mismatch、crash 和 secret sentinel negatives。
- 与 Codex 运行同 Harness profile-switch conformance；`claude-code` 仅在 14a 已交付时参与回归。

### Files

- `src/bora/config/model.py`
- `src/bora/config/load_and_lock.py`
- `src/bora/adapters/agent_registry.py`
- `src/bora/adapters/agent_pi.py`
- `tests/config/test_executor_capability_lock.py`
- `tests/executors/test_pi_executor.py`
- `tests/acceptance/test_builtin_executor_profile_switch.py`

### Acceptance Criteria

- [x] Fixed registry/capability lock 对未知或不兼容 profile fail closed，不扫描 entry points，lock 不包 credential value。
- [x] `pi` 真实 invoke/evaluator/trajectory 通过，缺 locator 时无 child/API effect。
- [x] Zhipu/provider credential 仅在 Adapter child 可见，全树 sentinel scan 零命中。
- [x] Codex regression 与 focused gates 通过；`claude-code` 可用时加入回归，缺失时 residual 保持诚实。

## Phase 3 (14c): `opencode` 与 mixed-profile isolation

### Goal

交付最低闭环的第三个 built-in executor，并证明同 Attempt 多 profile 的 session、ceiling 和 trajectory 不混淆。

### Tasks

- 实现 `opencode` Adapter、env allowlist、event/session/result normalization 与终止。
- 运行两 profile 顺序/并发 invoke，验证 Attempt/profile/session binding 与独立目录。
- 拒绝 cross-profile/cross-Attempt handle、轨迹覆盖与静默 fallback。

### Files

- `src/bora/adapters/agent_opencode.py`
- `tests/executors/test_opencode_executor.py`
- `tests/runtime/test_multi_profile_binding.py`
- `tests/acceptance/test_builtin_executor_mixed_profiles.py`

### Acceptance Criteria

- [x] `opencode` 真实 invoke/evaluator/trajectory 通过，缺 locator 路径 fail closed。
- [x] 混合两 profile 形成独立 invocation trees/metadata/accounting，且 lock 可重建。
- [x] Cross-profile/Attempt session 在外部 effect 前拒绝，focused gates 通过。

## Phase 4: Three-backend public conformance 与状态同步

### Goal

从 clean state 验证 `codex`、`pi`、`opencode`、混合 profile、负向边界与旧 journeys；`claude-code` 可用时追加 residual probe，然后同步文档。

### Tasks

- 使用 `.env` 仅作 runtime input，执行必需三后端单 profile 和两后端 mixed-profile public smokes；可用时追加 `claude-code`。
- 运行 capability/credential/session/fallback/security negatives 和 v0.13 回归。
- 同步 README/Architecture/AGENTS/Roadmap/Spec，文档中只写 env 名占位符和非敏感版本。

### Files

- `examples/core/builtin-executor-conformance/`
- `tests/acceptance/test_builtin_executor_cli.py`
- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/13-builtin-multi-executor-plan.md`

### Acceptance Criteria

- [x] `codex`、`pi`、`opencode` 每个至少一次真实 success + trajectory + evaluator，mixed-profile 通过；`claude-code` 为 success 或显式 residual。
- [x] 所有 expected failures 零 fallback/伪 PASS/secret leak，`.env` 未跟踪。
- [x] Frozen install、Ruff、Pyright、pytest、strict validator、relative links 与 `git diff --check` 通过。
- [x] 文档明确本版是 built-in registry，没有插件/marketplace 声明。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| CLI 升级导致参数/事件漂移 | Phase 0 冻结版本与属性 probe；lock/evidence 记录版本；不依赖漂移的私有文本 |
| 为统一后端而静默降级 | capability matrix 显式进 lock，要求不满足时 Attempt 前 typed fail |
| 整个 host env 传给 child | per-executor env allowlist + empty-base environment + sentinel scan |
| 把 fixed registry 误称插件 | 禁止 entry-point scan/package loading；README/Roadmap 明确 built-in only |
| 多 profile 覆盖 trajectory/session | identity 绑 Attempt+profile+executor，独立目录和 negative tests |

## User Acceptance

- [x] 用户接受 v0.14 最低为 `codex` + `pi` + `opencode`、14a `claude-code` 在 PATH/account 缺失时保持 residual、`.env` 只作宿主 locator 值源，并在规划验收之后单独明确授权实施。


## Evaluation Record

### Round 1

- Critic: independent subagent (019fc73a-a8f8-70d0-b2b2-c4b4dce84980; 2026-08-03)
- Review scope: full
- Evidence reviewed: real codex/pi/opencode PASS on builtin-executor-conformance; mixed codex+pi independent trees; unit executor/security suites; residual claude-code PATH missing
- Findings: F1 capability matrix not in lock; F2 SDK dropped invocation_id; F3 entry points still preferred; F4 zhipu_coding_api_key alias; F5-F8 low
- Selected fixes: F1 lock.json capabilities snapshot; F2 SDK pass-through invocation_id; F4 ZAI alias mapping
- Executor fixes: applied F1/F2/F4 same cycle
- Deferred findings: F3 entry-point precedence residual to plugin Spec; claude-code residual (PATH missing)
- Validation rerun: three-backend public smokes PASS; mixed PASS; uv run pytest tests/executors -q (12 passed); ruff clean on touched adapters
- Verdict: pass-with-follow-ups
- Version Index v0.14: AUTHORIZE_CHECK
