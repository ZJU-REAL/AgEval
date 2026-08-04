# Spec 14 — Docker L1 可见性与隔离收口

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.15`；Docker Attempt、executor execution location、workspace/secret/network projection、gold-not-mount、clean evaluator、evidence volume |
| Type | feat |
| Priority | P0 |
| Status | completed |
| Planning gate | closed |
| Completed | 2026-08-03 |
| Independent review | required |
| Dependencies | [Spec 12](12-attempt-evidence-trajectory-plan.md) 完成；[Spec 13](13-builtin-multi-executor-plan.md) 完成 |
| Decisions | [Roadmap v0.15](../ROADMAP.md#v015--docker-l1-可见性与隔离收口)、[Provider](../../docs/design/05-runtime-core.md#83-provider)、[物理可见性投影](../../docs/design/06-capability-adapter-visibility.md#104-prompt-隔离与物理隔离可见性投影)、[安全边界](../../docs/design/08-conversion-security-testing.md#18-安全与信任边界) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: 等待用户验收文档且 v0.13–v0.14 完成；此前不运行 Docker 或改 production code。

### Current blockers

- None.

### Potential blockers

- None.

## Phases

- [x] Phase 0: image/platform、executor location、mount/network/credential/evidence 真实 probes
- [x] Phase 1: DockerProvider 与 per-profile 物理 projection
- [x] Phase 2: gold-not-mount、writer barrier、evidence export 与 clean evaluator
- [x] Phase 3: L1 success/negative public matrix、回归与状态同步

## Background

### Problem

说「有 Docker / L1」不等于 Agent **真的**只看得到该看的目录、碰不到答案文件、连不了不该连的网。  
换一批后端（容器里跑 CLI vs 宿主机调 API）后，运行位置和轨迹写入路径都可能变；不能拿旧 journey 的成功自动盖章。

### Current Behavior

- 部分路径已证明 harness + 干净评测容器；Agent 仍可能在宿主进程里跑。
- v0.14 会引入形态不同的内置后端，L1 声明必须**按后端实测**，不能继承。
- 标准答案 / gold 必须靠**不挂载** + 评测前再拷贝，不能靠「配置里删字段」或 prompt 里装没看见。

### Goals and Non-goals

- Goal: 每个 profile 写清楚：**实际跑在哪**（容器 / 宿主 API 客户端）、镜像与平台、可读可写路径、网络与密钥可见范围。
- Goal: 能进容器的 CLI 后端尽量进容器；只能宿主调 API 的，诚实写 location，**不假装** Agent 也在容器隔离里。
- Goal: 轨迹写到宿主可控的 evidence 目录；容器不能改别的 Attempt，也不能改已封存文件。
- Non-goal: 不做 VM、完整 L2、把 Docker socket 交给任务、跨机调度。
- Non-goal: 不因「起了个容器」或单个后端成功就宣称全面 `isolated`。
- Evidence boundary: `assurance:l1` 只覆盖 Result 里写明且正负探针都过的那一组合。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora run <package> --task <task-id>` with locked built-in profile。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: v0.14 single/mixed-profile success、credential/capability negatives 与 v0.13 trajectory scans。
- Observable result: 多后端能跑能落盘；**谁看得见什么**尚未按后端闭合。

### User Story

作为操作者，我按声明的 Docker L1 跑一次任务后，能从 Result/evidence 看清：Agent **实际跑在哪**、它读不到 gold、连不了未声明的网；评测容器只拿到允许的输入。做不到的隔离项不会被标成 `assurance:l1`。

### Scope Boundary

- Included: immutable Attempt image、actual executor location、path/secret/network projection、evidence volume、writer inventory、gold materialization、clean evaluator、L1 mechanism matrix。
- Deferred to `v0.16`: 真实 Environment 和多角色组合。
- Deferred to `v0.19+`: VM/L2/跨主机、完整 supply-chain signing 和远程 workers。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| v0.14 built-in executors + trajectory | `baseline-verified` | Spec 12–13 | 执行 `codex` + `pi` + `opencode` conformance；可用时附加 `claude-code` | 真实 invoke、lock matrix、独立 trajectory 通过 | 回收 child/session/run temp |
| Docker Engine/buildx | `external-accepted` | User-owned Docker Desktop/daemon | `docker version`、`docker buildx version`、非特权 probe | target platform 可 build/start/inspect/stop/remove，task 不见 socket | 删除本 Spec 创建的 container/network/volume/temp tag |
| Attempt image/location probes | `phase-produced` | Agent / Phase 0 | repository-owned Dockerfile/build lock 和各 executor probe | digest/platform/runtime ABI/location 可重建，无 L0 fallback | 删 temp tag/containers，保留 evidence 引用 digest |
| Projection/evidence/evaluator mechanisms | `phase-produced` | Agent / Phase 0–2 | Attempt-scoped mounts/network/credential/evidence volume 与 clean evaluator | property-level allow/deny/writer/gold probes | 按 owner 逆序 teardown，状态不明资源禁止复用 |
| L1 visibility mechanism packages | `phase-produced` | Agent / Phase 3；`examples/l1/builtin-executor-visibility/` 与 `examples/l1/builtin-executor-visibility-denied/` | 创建容器内 CLI success 与 gold/path/network/secret/writer 机制 tasks | success 与每个 expected failure 经 production CLI 独立命中预期 stable kind | 删本 Attempt container/network/volume/temp evidence；tracked packages 保留 |

</details>

### Runnable Acceptance

- Success smoke: `uv run bora run examples/l1/builtin-executor-visibility --task builtin-executor-visibility`，真实 CLI executor 位于 Attempt container。
- Expected failure: gold/evaluation read、cross-view write、undeclared endpoint、missing secret grant 以机制 task 分别验证，不共用一个不可定位失败。
- Regression smokes: v0.13 trajectory、v0.14 required three-backend conformance（及可用时的 `claude-code` residual）、旧 L0/L1 provider negatives。
- Observable evidence: image/platform/executor location、mount/network/credential policy digests、writer confirmation、materialization manifest、trajectory locator。

### Extension Seams

- `ExecutionLocation`: `attempt-container` / `parent-api-client` 作证据事实，不隐藏后端差异。
- `EvidenceVolume`: filesystem bind/volume 实现保持 replaceable，当前不引入 remote store。

## Design

> Inherited design: [可见性红线](../../docs/design/00-overview-and-product.md#04-可见性投影保留的一等机制)、[Provider](../../docs/design/05-runtime-core.md#83-provider)、[Workspace owner](../../docs/design/05-runtime-core.md#86-workspace-与-artifact-owner)、[Evaluator Runner](../../docs/design/05-runtime-core.md#87-evaluator-runner)
>
> Local delta: 将内置 executor 的 actual location 与 v0.13 evidence volume 纳入 L1 assurance，不重写既有 Provider contract。

### Visibility Matrix

| Consumer | Workspace | Secret | Network | Gold/evaluation | Evidence write |
| --- | --- | --- | --- | --- | --- |
| Harness | locked read/write views | none by default | declared Harness endpoints only | absent | Harness supplement only |
| Agent CLI | profile workspace view | executor-only locator values | profile endpoint class | absent | own invocation append handle |
| Parent API client | no implicit package root | executor-only values | profile endpoint class | absent | own invocation append handle |
| Evaluator | read-only materialized allowlist | evaluator-only if declared | default none | allowlisted after barrier | evaluator raw only |

### Failure and Cleanup Semantics

- image/platform/location mismatch、projection provision failure、gold mount 命中或 policy probe 失败均在 Harness 前 fail closed，不降级 L0。
- timeout/cancel/crash 进入 capability close → TERM/wait/KILL → writer confirm → evidence seal → cleanup；writer 未确认时 evaluator 零启动。
- cleanup warning 与 score 分离；未清理且状态不明的资源不进入后续 Attempt 复用池。

## Phase 0: L1 真实 property probes

### Goal

在实现前逐 executor 证明 image/location、mount、network、credential、evidence 和 writer 机制。

### Tasks

- 冻结 Attempt image/platform/digest/runtime ABI，探测必需三后端容器化和 API-client fallback 的实际边界；`claude-code` 仅在 v0.14 已交付时参与。
- 在容器内执行 read/write/absent/symlink/traversal、network allow/deny/redirect、credential sentinel 和 evidence cross-write probes。
- 验证 residual writer 终止与无后续写，无法证明的属性不进 L1 claim。

### Files

- `docker/attempt/Dockerfile`
- `src/bora/adapters/provider_docker.py`
- `tests/provider_l1/test_builtin_executor_location.py`
- `tests/provider_l1/test_evidence_volume.py`
- `tests/provider_l1/test_projection_property_matrix.py`

### Acceptance Criteria

- [x] 每个 executor 都有 requested/actual location 和可重复证据，容器不可用时不伪称 L1。
- [x] Mount/network/secret/gold/evidence/writer 属性均通过真实 Docker 正负 probe，无 host 副作。
- [x] `R1`–`R2` 关闭或路由 Research，未闭合时不进入 Phase 1。

## Phase 1: DockerProvider 与 per-profile projection

### Goal

将已证明的 image/location/view/network/credential/evidence 机制接入 production composition。

### Tasks

- 扩展 Provider outcome 记录 actual location 与 assurance facts，按 Attempt/profile 生成 mount/network/credential plan。
- 将 CLI executor 放入 container，API-client 以明确 parent boundary 受控运行；均不获得整个 host env/root。
- 让 evidence handle 只能追加本 invocation，seal 后只读，cleanup 按 owner 幂等执行。

### Files

- `src/bora/provider/contract.py`
- `src/bora/provider/outcomes.py`
- `src/bora/adapters/provider_docker.py`
- `src/bora/adapters/credential_projection.py`
- `src/bora/application/composition.py`
- `tests/provider_l1/test_docker_provider.py`
- `tests/security/test_profile_projection.py`

### Acceptance Criteria

- [x] Production path 在 Harness 前固定 actual image/platform/location/views/network/credential/evidence identities，任一缺失均无 fallback。
- [x] Harness/Agent/API client 只获得声明视图，Adapter 无 Benchmark/task/role 分支。
- [x] Partial prepare/start/cancel/timeout 均进入同一资源 owner cleanup，focused gates 通过。

## Phase 2: Gold barrier、writer 与 clean evaluator

### Goal

在新 executor/evidence volume 组合上闭合 writer stop 和 evaluator-only materialization。

### Tasks

- 登记 Harness/Agent/API-client/tool 所有 writer，capability close 后终止并确认。
- 仅在 writer 终态和 declared output 完整时 materialize allowlisted inputs 到新只读 evaluator runtime。
- 验证 evaluator 无 Agent secret/network/mutable workspace/full trajectory，Result 分离 evaluation/cleanup。

### Files

- `src/bora/evaluation/result_binding.py`
- `src/bora/application/run_l1.py`
- `tests/provider_l1/test_writer_barrier_multi_executor.py`
- `tests/acceptance/test_clean_evaluator_visibility.py`
- `tests/security/test_gold_not_mounted.py`

### Acceptance Criteria

- [x] Gold/evaluation 在 Harness/Agent runtime 始终 absent，仅 barrier 后按 allowlist 进 clean evaluator。
- [x] Residual writer/input digest change 使 evaluator start count=0，partial trajectory 仍可解析。
- [x] Evaluator raw、score、runtime error、trajectory 和 cleanup warning 保持独立，focused gates 通过。

## Phase 3: L1 public matrix 与状态同步

### Goal

用 production CLI 完成一个容器内 executor success、可见性 negatives、writer negative 和旧回归。

### Tasks

- 运行 mechanism-named L1 success/path/network/secret/gold/writer journeys，记录 actual assurance facts。
- 回归 v0.13–v0.14 和旧 L0/L1 suites，扫描 credential/hidden/host paths。
- 同步 README、Architecture、AGENTS、Roadmap 和 Spec，限定 L1 声明。

### Files

- `examples/l1/builtin-executor-visibility/`
- `examples/l1/builtin-executor-visibility-denied/`
- `tests/acceptance/test_builtin_executor_l1_cli.py`
- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/14-docker-l1-visibility-plan.md`

### Acceptance Criteria

- [x] Success 与四类可见性/writer expected failures 经 public CLI 通过，无 L0 fallback。
- [x] 证据可关联 image/platform/location/policies/writers/materialization/trajectory，不含 secret/hidden bytes。
- [x] Frozen install、Ruff、Pyright、pytest、Docker probes、strict validator、relative links 与 `git diff --check` 通过。
- [x] 只在限定组合上声称 `assurance:l1`，不声称全面 `isolated` / `real-benchmark-verified`。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 容器存在被写成隔离证据 | 逐属性 allow/deny probe + actual assurance 字段，缺一项不升级 |
| Parent API-client 被隐藏 | Result/evidence 显式 `execution_location`，只声称已物理强制的属性 |
| Evidence volume 成为跨 Attempt 写通道 | per-invocation append handle、Attempt ownership、seal read-only、cross-write negative |
| Gold 仅从 config 删除 | 物理 absent mount + barrier 后新 evaluator volume + hidden-byte scan |
| Docker cleanup 留下可复用资源 | owner inventory、逆序幂等 teardown、unknown state 禁止复用 |

## User Acceptance

- [x] 用户接受 Docker L1 主线、API-client actual-location 诚实边界、property-level probes 与限定 assurance 声明，并明确授权 Docker/真实 Agent 实施与 E2E。


## Evaluation Record

### Round 1

- Critic: independent subagent (019fc742-e166-73d1-afde-ce5b7bb356e9; 2026-08-03)
- Review scope: full
- Evidence reviewed: examples/l1/builtin-executor-visibility PASS assurance:l1 with execution_location; gold-denied probe; tests/provider_l1 10 passed
- Findings: F1 parent-api-client residual for Agent (honest location); F2 weak denied test; F3 docs sync
- Selected fixes: docs/README sync; keep residual honesty for containerized CLI agent
- Executor fixes: none blocking
- Deferred findings: containerized codex remains residual when agent is parent-api-client; recorded honestly
- Validation rerun: pytest provider_l1 + public visibility smoke PASS; ruff clean on run_l1
- Verdict: pass-with-follow-ups
- Version Index v0.15: AUTHORIZE_CHECK
