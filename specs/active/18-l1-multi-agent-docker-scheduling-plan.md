# Spec 18 — L1 多 Actor Docker 隔离与 SDK 调度

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-04 |
| Scope | Docker L1 下 SDK session/invoke 容器内执行、`agent_isolation` lock、`shared-container`、`container-per-group` 与 one-shot residual 收口 |
| Type | feat |
| Priority | P0 |
| Status | planning |
| Planning gate | open — design synchronized; implementation not authorized |
| Completed | pending |
| Independent review | off |
| Dependencies | [L1 multi-agent constitution](../constitution/2026-08-04-l1-multi-agent-docker-isolation.md) active；仓库 `docker/attempt/Dockerfile` + `docker/attempt/build.py` 官方 image 路径；package `environment/Dockerfile` 构建路径；既有 ParentAgentService / SDK Session 与 Docker L1 baseline |
| Decisions | [L1 多 Actor 隔离与 SDK 调度面](../../docs/design/05-runtime-core.md#l1-多-actor-隔离与-sdk-调度面)、[L1 多 Actor agent_isolation](../../docs/design/02-task-package-and-config.md#l1-多-actor-agent_isolation)、[L1 多 Actor Session](../../docs/design/04-harness-core-sdk.md#l1-多-actor-session-与-loop-内上下文)、[文件共享](../../docs/design/06-capability-adapter-visibility.md#103-文件共享) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `no` |
| User decision required | `yes` |
| Ready for acceptance now | `no` |
| Current blockers | `1` |
| Potential blockers | `2` |

- Next action: 等待独立实现授权；获准后从 Phase 0 的单 actor SDK→L1 target real probe 开始，不先实现隔离拓扑。

### Current blockers

- `B1` (Owner: User): 本轮仅授权设计与 Spec 同步，未授权修改 production code、运行 Docker/真实 Agent 实施门禁或改变发布状态。

### Potential blockers

- `R1` (Owner: Agent / Phase 0): worker-local scoped channel 跨 Harness container 到 ParentAgentService 的 transport、权限、关闭与 relay crash 行为尚未通过真实 Docker probe。
- `R2` (Owner: Agent / Phase 2): first-party CLI executor 以多个 non-root numeric UID、私有 HOME 与 scoped credential 运行的兼容性尚未逐后端证明。

## Phases

- [ ] Phase 0: 单 actor SDK L1 parity 与 in-target exec
- [ ] Phase 1: `agent_isolation` lock、logical mapping 与 prepare topology
- [ ] Phase 2: `shared-container` multi-UID、private HOME 与 `shared_write`
- [ ] Phase 3: `container-per-group`、generation fencing 与跨组 memory context
- [ ] Phase 4: public examples、one-shot residual quarantine、回归与文档收口

## Background

### Problem

当前 L0 已有 SDK `Agent.session().invoke()` → ParentAgentService 的多轮路径，Docker L1 也已有 repository-owned base image、package `environment/Dockerfile`、containerized CLI 与 clean evaluator 切片。两条路径尚未合并：L1 Agent 仍可由 Runtime 从 `parameters.question` 发起一次直接 CLI invoke，Harness 不能在相同 L1 authority 下按 actor/profile 打开多轮 session。容器存在本身也没有定义多 actor 的 UID、HOME、共享写目录和 target mapping。

### Current Behavior

- `docker/attempt/Dockerfile` 与 `docker/attempt/build.py` 提供 `bora-attempt:l1` build/lock 路径；L1 package 通过 `environment/Dockerfile` 生成 Attempt image。
- ParentAgentService 已拥有 opaque session、执行前 invocation ceiling、trajectory 与 close；SDK 的 session channel 目前证明的是 L0 worker 路径。
- Docker L1 one-shot 路径可在容器中执行 CLI，但 `parameters.question` 不是 Harness multi-agent scheduling surface。
- Config lock 尚无 `provider.agent_isolation`，Runtime 也没有 actor→target 与 session→target generation mapping。

### Goals and Non-goals

- Goal: L1 Harness 使用与 L0 相同的 `Agent.session(profile_id, actor_id=..., max_turns=...)` → `invoke` / `close` 表面，并由 ParentAgentService 保持 session、hard ceiling、trajectory 与外部 Agent effect authority。
- Goal: 实现 lock-safe logical topology、Attempt-private physical mapping、`shared-container` 与 `container-per-group` 两档明确保证。
- Goal: 缺 binary、credential、target、relay、UID capability 或 generation 时 fail closed，任何 L1 invoke failure 都不回退 host CLI。
- Non-goal: 本 Spec **不编辑 `specs/ROADMAP.md`、不勾 Roadmap checkbox，也不创建新的版本完成声明**。
- Non-goal: mid-loop Runtime handoff / Core-aware mailbox / immutable materialize 延后到 [GitHub issue #2](https://github.com/ffy6511/BORA/issues/2)；本 Spec 仅使用 Harness memory / prompt，Core unaware。
- Non-goal: dynamic actor、Attempt 内 regroup、overlapping groups、cross-Attempt reuse、durable reopen、Kubernetes、多机、VM 或 L2 hostile multi-tenant guarantee。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora run <package> --task <task-id>`。
- Production composition root: `src/bora/application/composition.py` 及现有 `run` application path。
- Baseline smokes: L0 `examples/core/sdk-agent-session` multi-invoke；L1 `examples/l1/builtin-executor-visibility` container execution + clean evaluator。
- Observable result: SDK multi-turn 与 Docker L1 分别可运行；没有一条 public journey 同时证明 SDK scheduling、actor mapping、multi-UID/group isolation 与 no-host-fallback。

### User Story

作为 Harness 作者，我在 Docker L1 Attempt 中可以按声明的 `actor_id` 和 profile 打开多个 SDK session，让每次 invoke 只在 Runtime 绑定的容器 target、UID/GID、HOME、workspace、network 与 credential projection 下执行；我仍用普通 Python memory 组织角色上下文，容器或 relay 失败时得到明确错误且绝不会静默改走宿主机。

### Scope Boundary

- Included: SDK open/invoke/close relay、ParentAgentService actor/profile/target binding、Provider in-target exec、logical/physical/session mapping、两种 isolation mode、private HOME、shared GID + `shared_write`、generation fencing、writer/cleanup/evidence、one-shot residual quarantine。
- Deferred: issue #2 mid-loop physical handoff、cross-container RW、durable mailbox/reopen、per-group network、container-per-invocation、L2/VM/multi-host。
- Status boundary: 全部 Phase 与 public matrix 通过前只称 planning / not implemented；本 Spec 不更新 Roadmap。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| ParentAgentService + SDK Session baseline | `baseline-verified` | Existing L0 SDK path | 运行 `examples/core/sdk-agent-session` 的 production CLI success / offline failure | opaque session、multi-invoke、ceiling、close 与 trajectory 关联 | worker/session/run temp 由现有 lifecycle 回收 |
| Official L1 base + package image path | `baseline-verified` | `docker/attempt/Dockerfile`、`docker/attempt/build.py`、package `environment/Dockerfile` | `uv run python docker/attempt/build.py --platform linux/arm64`；public run 构建 package image | image/platform/digest 与 package Dockerfile 可定位，container 内 executor 存在 | 删除本 Spec 创建的 temp tag/container；保留 digest evidence |
| Docker Engine/buildx | `external-accepted` | User-owned Docker daemon | Phase 0 preflight `docker version` / `docker buildx version`，不把 socket交给 task | build/start/exec/stop/remove 与 no-docker.sock property probes | 删除本 Spec 创建的 container/network/volume/tag |
| Scoped SDK relay + in-target exec | `phase-produced` | Agent / Phase 0 | 将 Harness worker 的 scoped channel 接到 ParentAgentService 与 Provider exec | single actor 多 invoke 全在 `attempt-container`，relay/missing target 零 host effect | close relay/session，kill process group，remove target |
| `agent_isolation` lock + prepare topology | `phase-produced` | Agent / Phase 1 | Config validate/canonicalize logical groups；Provider prepare materialize targets | invalid actor/profile/path/mode 零 Harness start；mapping 无 raw handle 泄漏 | partial prepare 按 private ledger 逆序清理 |
| Multi-UID/private HOME/shared path | `phase-produced` | Agent / Phase 2 | 为 shared container 创建 actor UID/HOME/shared GID grants | HOME/credential/cross-write allow/deny 与 unsupported CLI probes | 删除 actor-private credential copies/HOME/container |
| Per-group containers + generation ledger | `phase-produced` | Agent / Phase 3 | 每 group 创建 target；session bind target generation | cross-group RW absent、dead/stale target fail closed、memory prompt context success | stop writers、fail sessions、remove all targets，再进入 evaluator barrier |
| Real executor credential capability | `external-accepted` | User-managed credential store / existing logical locator | Runtime 只按 profile locator copy/inject 最小材料；文档和 example 不含值 | credential missing 在 CLI start 前失败；全 evidence/snapshot sentinel scan 零命中 | 删除 Attempt-private copies，不修改宿主 credential source |

</details>

### Runnable Acceptance

- Success smoke A: `shared-container` package 由 L1 Harness 通过 SDK 打开至少两个 actor session；不同 UID/private HOME，允许的 `shared_write` 成功，非共享路径互相拒绝，独立 evaluator 给出 Result。
- Success smoke B: `container-per-group` package 在至少两个 group target 中完成 SDK invokes；跨组文本由 Harness memory 拼入 prompt，无跨容器 RW mount，终局 output 经 `publish_*` 进入 evaluator。
- Expected failures: missing/unknown actor、profile allowlist violation、missing credential、unsupported numeric UID、relay crash、dead target、generation mismatch、cross-group write 与 residual writer 分别命中 stable kind；external invoke/host fallback counter 均为零。
- Regression smokes: L0 SDK session、既有 Docker L1 visibility/gold/writer negatives、multi-profile hard ceilings、trajectory seal/export 与 clean evaluator。
- Observable evidence: logical topology digest、opaque target id、actual isolation mode、image digest、actor/profile/session/invocation mapping、UID/GID class（无 host identity）、execution location、writer/cleanup outcome；不含 Docker handle、socket path、credential、HOME bytes 或 gold。

### Extension Seams

- `ExecutionTarget`: Provider 私有 target contract 可由未来 VM 实现替换；当前只实现 Docker，不把 Docker id 暴露给 Core client。
- Capability channel: 保持 open/invoke/close framing 与 transport 分离；当前只实现 scoped local relay，不实现 durable mailbox。
- Mid-loop data: Harness memory 与终局 `publish_*` 分离，未来 `handoff_*` 不复用 evaluator/PASS authority。

## Design

> Inherited design: [L1 multi-agent constitution](../constitution/2026-08-04-l1-multi-agent-docker-isolation.md#decision)、[Provider / SDK 调度](../../docs/design/05-runtime-core.md#l1-多-actor-隔离与-sdk-调度面)、[Config YAML](../../docs/design/02-task-package-and-config.md#l1-多-actor-agent_isolation)、[SDK Session](../../docs/design/04-harness-core-sdk.md#l1-多-actor-session-与-loop-内上下文)、[可见性](../../docs/design/06-capability-adapter-visibility.md#103-文件共享)
>
> Local delta: 把已有 L0 ParentAgentService/SDK 与已有 Docker L1 image/Provider 合并为 actor-bound SDK scheduling path，再依次增加 lock topology、shared container 和 per-group container；不扩展 Runtime workflow 或中途 handoff。

### Control Flow

```text
load_and_lock(agent_isolation logical topology)
  → build package image
  → Provider.prepare Harness target + Agent ExecutionTargets
  → start task worker only after all required targets exist
  → SDK open(actor_id, profile_id)
  → ParentAgentService validate allowlist + bind target/generation
  → SDK invoke(session_id, prompt)
  → reserve hard ceiling
  → Provider.exec(target, actor uid/gid, scoped env)
  → seal invocation trajectory
  → return normalized result
  → close/cancel/timeout: close effects → kill writers → fail sessions → cleanup targets
  → evaluator barrier
```

### Mapping and Visibility

| Mapping | Authority | Persisted/public fields | Private-only fields |
| --- | --- | --- | --- |
| Logical | Config lock | actor id、group id、allowed profile ids、mode、`shared_write` | none |
| Physical | Provider Attempt ledger | opaque target id、image digest、actual mode | Docker id、UID/GID number、socket path、live handle |
| Session | ParentAgentService | opaque session id、actor/profile/invocation refs | target handle、credential material、relay internals |

`actor_id` 是隔离 principal；profile 是可被多个 actor 复用的 executor/model/credential template。Container 不能按 profile id 单独建 key。Prepare 先完成全部 required target，任一失败时 Harness 不启动。

### Isolation Guarantees

| Mode | v1 guarantee | Explicit limit |
| --- | --- | --- |
| `shared-container` | distinct numeric UID、HOME 0700、actor-private credential copy；same group 可选 shared GID，只写 `shared_write` | 不承诺 per-actor PID/network namespace；executor 不支持 non-root 时 fail closed |
| `container-per-group` | one container per group；single actor group 即 per-agent；filesystem boundary stronger | 无跨 container RW volume；非 L2 hostile tenant promise |

所有 Agent target 使用同一 Attempt-level `provider.network: bridge | none`。Harness/Evaluator 沿用各自更窄策略；task 不见 Docker socket。

### Mid-loop Context and Artifacts

- 同 Harness 进程的中间文本、JSON-compatible object 与角色结果保存在 Harness/upstream memory，并显式拼入后续 prompt；Core unaware。
- `shared_write` 是同 shared container 内的可变文件协作 grant，不是 handoff API。
- `publish_*` 只提交终局 declared artifact；issue #2 的未来 `handoff_*` 不自动进入 `evaluation.inputs`，也不拥有 PASS authority。
- Gold/evaluator-only material从未挂给 Harness/Agent，也不能成为 handoff source。

### Failure, Concurrency and Cleanup

- 同一 session 的 invokes 串行；不同 session 仅在 hard ceiling 与 Provider capacity 允许时并发。
- Unknown actor/profile、closed session、dead/stale target、relay/credential/CLI failure 均在外部 effect 前或当前 invoke 边界失败；禁止 host fallback。
- Cancel/timeout/worker crash 先拒绝新 effect，再终止 process group、标记 session failed、确认 writer stop、seal partial trajectory、逆序移除 targets；writer 未确认时 evaluator 不启动。
- Cleanup warning 与既有 Result/score 分离；状态未知的 target 不复用。

## Phase 0: SDK L1 parity — single actor

### Goal

让单 actor/single group 的 L1 Harness 经 SDK session/invoke 调用 ParentAgentService，并把 Executor effect 放进已绑定 Docker target。

### Tasks

- 在 L1 Harness worker 中建立 scoped open/invoke/close channel；task 无 Docker socket、raw handle 或宿主 credential view。
- 扩展 session open 接收 L1 必填 `actor_id`，先以单 actor implicit topology 验证 Parent authority、hard ceiling 与 trajectory。
- Provider 增加 target-bound exec + process-group lifecycle；隔离 one-shot direct invoke，不允许失败后回退 host。
- 真实 probe relay close/crash、missing binary/credential、timeout/cancel 与 invocation N+1。

### Files

- `sdk/python/src/bora_sdk/agent.py`
- `src/bora/runtime/agent_service.py`
- `src/bora/provider/contract.py`
- `src/bora/adapters/provider_docker.py`
- `src/bora/application/run_l1.py`
- `src/bora/runtime/task_worker.py`
- `tests/provider_l1/test_sdk_container_session.py`
- `tests/acceptance/test_l1_sdk_single_actor.py`

### Acceptance Criteria

- [ ] L1 public path 的至少两次 SDK invoke 均记录 `attempt-container`、同 actor/session 与独立 invocation evidence，ParentAgentService 仍是唯一 ceiling/trajectory authority。
- [ ] relay、binary、credential、target 或 deadline failure 不触发 host executor，独立外部 counter 为零。
- [ ] Harness/container 无 Docker socket/raw handle/host HOME，focused unit、integration 与 real Docker probes 通过。

## Phase 1: `agent_isolation` lock and prepare topology

### Goal

锁定 logical group/actor/profile/shared-write topology，并在 Harness 启动前 materialize Attempt-private targets。

### Tasks

- 增加 schema/model/canonical lock 与 fail-closed validation；禁止 physical/runtime 字段进入 YAML/lock。
- 建立 actor→ExecutionTarget 与 session→target generation ledger；profile 只作 allowlisted execution template。
- Partial prepare 失败时不启动 Harness，清理所有已创建 target 并记录 typed prepare error。

### Files

- `src/bora/config/model.py`
- `src/bora/config/load_and_lock.py`
- `src/bora/provider/contract.py`
- `src/bora/provider/outcomes.py`
- `src/bora/adapters/provider_docker.py`
- `tests/config/test_agent_isolation.py`
- `tests/provider_l1/test_agent_target_mapping.py`

### Acceptance Criteria

- [ ] mode/group/actor/profile/shared_write/network 全部正负 schema/property tests 通过；invalid config 零 container/Harness start。
- [ ] Docker handle、numeric UID/GID、socket path、runtime network name 与 credential value 不进入 lock、SDK response 或公开 evidence。
- [ ] actor/profile allowlist 与 generation 绑定发生在 parent authority，focused gates 通过。

## Phase 2: `shared-container`

### Goal

在一个 Agent container 内用 multi-UID、private HOME 与显式 shared GID/path 提供低档多 actor 隔离。

### Tasks

- 为 actor 分配 Attempt-private numeric UID、HOME 0700、credential copy 与 process identity；启用 no-new-privileges、无 docker.sock。
- 仅对 group `shared_write` 与各 actor WorkspaceView write 交集配置 shared GID；其余路径按 actor 拒绝。
- 为每个 first-party executor 运行 non-root capability probe；不支持的组合返回 `unsupported_capability`。
- 验证 same-session serialization 与不同 session 在 ceiling 允许时的并发。

### Files

- `src/bora/adapters/provider_docker.py`
- `src/bora/adapters/credential_projection.py`
- `src/bora/provider/workspace_plan.py`
- `tests/provider_l1/test_shared_container_multi_uid.py`
- `tests/security/test_actor_home_credentials.py`
- `tests/security/test_shared_write_projection.py`

### Acceptance Criteria

- [ ] 两 actor 的 UID/HOME/credential 私有性和 non-shared path allow/deny 通过真实容器 property probes。
- [ ] 只有 WorkspaceView write 交集内的显式 `shared_write` 可由 shared GID 协作，traversal/symlink/cross-write 全拒绝。
- [ ] Unsupported executor 不提权、不改 mode、不回退 host；partial writers 与 cleanup 有界。

## Phase 3: `container-per-group`

### Goal

为每个 logical group 建立独立 target，并在无跨容器 RW volume 的前提下完成多组 SDK workflow。

### Tasks

- Prepare one target per group；single actor group 保持相同 contract，不引入 per-profile container key。
- 绑定 session target generation；target death/recreate 后旧 session 永久拒绝。
- 用 Harness memory / prompt 在 group 间传递文本/结构化上下文；终局输出才调用 `publish_*`。
- 验证 cancel/timeout/worker crash 对所有 group writer 的 termination、barrier 与 cleanup 顺序。

### Files

- `src/bora/runtime/agent_service.py`
- `src/bora/adapters/provider_docker.py`
- `src/bora/application/run_l1.py`
- `tests/provider_l1/test_container_per_group.py`
- `tests/runtime/test_target_generation.py`
- `tests/acceptance/test_l1_multi_group_memory_context.py`

### Acceptance Criteria

- [ ] 两 group 在不同 container target 中完成 SDK invokes；跨组文本只经 Harness prompt，mount inventory 无 cross-container RW。
- [ ] Dead target/generation mismatch/partial prepare 均 fail closed，无新 invoke、无 host fallback、无陈旧 session reuse。
- [ ] 所有 writer 停止后才 materialize evaluator input；cleanup inventory 为空或产生不改 score 的明确 warning。

## Phase 4: Public examples and residual quarantine

### Goal

用 mechanism-named examples 闭合两档隔离与失败矩阵，并把 `parameters.question` one-shot 明确隔离为 residual。

### Tasks

- 新增 `shared-container` 与 `container-per-group` public packages，使用 SDK session、Harness memory 与终局 `publish_*`。
- 新增 actor/profile/UID/relay/target/generation/shared-write/writer expected-failure journeys 和 host-fallback counter。
- one-shot 路径加 compatibility/residual 标识、禁止进入 multi-agent acceptance 与 stronger assurance claim；不删除仍被既有 smoke 使用的路径。
- 回归 L0 SDK、L1 visibility/gold/writer、multi-profile/hard-ceiling/trajectory；同步 README、Architecture 与本 Spec，明确**不编辑 ROADMAP**。

### Files

- `examples/l1/multi-agent-shared-container/`
- `examples/l1/multi-agent-container-per-group/`
- `tests/acceptance/test_l1_multi_agent_scheduling.py`
- `README.md`
- `ARCHITECTURE.md`
- `docs/design/02-task-package-and-config.md`
- `docs/design/03-harness-layer.md`
- `docs/design/04-harness-core-sdk.md`
- `docs/design/05-runtime-core.md`
- `docs/design/06-capability-adapter-visibility.md`
- `specs/active/18-l1-multi-agent-docker-scheduling-plan.md`

### Acceptance Criteria

- [ ] 两个 public success journeys 与每类 expected failure 经 production CLI 通过，evidence 可关联 actor/profile/session/target/mode/image/writer/cleanup。
- [ ] one-shot residual 不能满足本 Spec success smoke，任何 L1 invoke failure 均无 host fallback。
- [ ] Frozen install、Ruff、Pyright、pytest、real Docker/Agent smokes、secret/gold/handle scans、strict Specs validator、relative links 与 `git diff --check` 通过。
- [ ] 文档只声明实测 mode/executor/platform 组合，不扩写 L2、全 suite `isolated`、Runtime handoff 或 Roadmap 完成状态。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 复用 one-shot 路径伪装 SDK parity | public acceptance 必须由 Harness worker 调 `Agent.session(..., actor_id=...)` 多次 invoke，并检查 Parent evidence |
| Profile 被误作 isolation principal | lock/mapping/tests 全部以 actor id 建 target；profile 只在 actor allowlist 内选 executor template |
| shared container 的 UID 只是 metadata | 容器内 id/HOME/path/credential property probes + cross-write negatives；unsupported 组合 fail closed |
| Relay 暴露 host control plane | scoped channel 只开放 open/invoke/close；无 Docker socket/raw handle；worker/target teardown 时立即关闭 |
| 跨组协作诱发 RW volume 或 gold 泄漏 | v1 只用 Harness memory/prompt；gold 永不挂载；physical handoff 转 issue #2 |
| Spec 被误读为发布状态 | Metadata 保持 planning/open，全部 Phase unchecked，并明确不编辑 Roadmap |

## User Acceptance

- [x] 用户批准 constitution 方向并授权同步 design docs 与本 planning Spec。
- [ ] 用户另行授权 production code、Docker/真实 Agent implementation gates 与完成态变更。
