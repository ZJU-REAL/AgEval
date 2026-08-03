# Spec 15 — 多 profile 编排与 Environment 资源边界

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.16`；package-owned multi-profile workflow、Environment prepare/action/teardown、effect evidence、resource visibility 与 clean evaluation |
| Type | feat |
| Priority | P0 |
| Status | in-progress |
| Planning gate | review（待用户验收；implementation not started） |
| Completed | pending |
| Independent review | off |
| Dependencies | [Spec 13](13-builtin-multi-executor-plan.md) 完成；[Spec 14](14-docker-l1-visibility-plan.md) 完成 |
| Decisions | [Roadmap v0.16](../ROADMAP.md#v016--多-profile-编排与-environment-资源边界)、[Environment Manager](../../docs/design/05-runtime-core.md#85-environment-manager)、[普通 Agent 间传递](../../docs/design/06-capability-adapter-visibility.md#102-普通-agent-间传递)、[Adapter 准入](../../docs/design/06-capability-adapter-visibility.md#93-adapter-准入) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `no` |
| User decision required | `yes` |
| Ready for acceptance now | `yes` |
| Current blockers | `1` |
| Potential blockers | `2` |

- Next action: 等待用户验收文档且 v0.14–v0.15 完成；此前不改 Environment production path。

### Current blockers

- `B1` (Owner: User): 本轮只授权文档，依赖的 multi-executor/Docker L1 checkpoints 尚未完成。

### Potential blockers

- `R1` (Owner: Agent / Phase 0): 现有 PostgreSQL Adapter/Environment Manager 是独立切片，在 Docker Attempt 中的 network、credential、teardown 和 evaluator projection 需真实闭环 probe。
- `R2` (Owner: Agent / Phase 0): 多 profile 与 Environment action 的 writer/effect owner inventory 是否能在 timeout/cancel 下完整收口尚未证明。

## Phases

- [ ] Phase 0: Docker PostgreSQL lifecycle、action authority、writer/effect 与 cleanup probes
- [ ] Phase 1: Environment Manager/Capability production close
- [ ] Phase 2: package-owned multi-profile orchestration 与 trajectory/effect composition
- [ ] Phase 3: composed public success/failure、回归与状态同步

## Background

### Problem

多角色剧本（谁先说、谁汇总、中间传什么）应该写在 package 的 harness 里；  
**数据库启停、谁有权改库、密钥、清理、评测输入**应该由 Runtime 管。  
两边串了就会出两种坏结果：要么 Core 长成第二套 workflow 引擎，要么 harness 直接拿到库密码，隔离和权限作废。

### Current Behavior

- 已有多 agent + Postgres 类 journey 和 Adapter **切片**；Docker 上完整的 Manager + Capability 组合还没收口。
- v0.14 有多 profile 调用，v0.15 有隔离与落盘；本版把它们和**一种真实资源**接到同一次 Attempt。
- Campaign 矩阵、后台恢复、通用 Handoff 服务不在本轴。

### Goals and Non-goals

- Goal: **同一次 Docker Attempt** 里：至少两个 profile 调 Agent、至少一次真实改库（或等价资源动作）、产出约定文件、独立评测、资源拆干净。
- Goal: 改库前 Runtime 先查「允不允许」；允许/拒绝写进 `effects.jsonl`。
- Goal: 库密码等只给 Environment Adapter；Agent/Harness 只做业务动作，看不到管理员密钥。
- Non-goal: Core 不新增「角色图 / 分支服务 / team memory」；中间业务数据仍在 package `lib/`。
- Non-goal: Adapter 不按 benchmark 名分支，只认资源类型（如 postgresql）和锁定配置。
- Non-goal: 不做 Campaign 全文、插件、后台 reopen、VM、上游 suite 认证。
- Evidence boundary: 只证明「Docker + PostgreSQL + 内置 profile」这一组合机制。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: Docker L1 `uv run bora run <package> --task <task-id>` with built-in profiles。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: v0.15 containerized executor success、visibility/writer negatives 和 clean evaluator。
- Observable result: 多 profile 与隔离能跑；**同 Attempt 真资源**尚未完整组合验收。

### User Story

作为 Harness 作者，我在 package 里写好多角色顺序（谁调用哪个 profile、中间数据怎么传），BORA 负责：在允许的动作里改数据库、拦不允许的动作、落盘轨迹与效果摘要、评测后拆资源——**不把我的剧本搬进 Core**。

### Scope Boundary

- Included: PostgreSQL prepare/health/action/teardown、Capability proxy、resource credential/network projection、multi-profile package workflow、effects/trajectory/evaluation/cleanup composition。
- Deferred to `v0.17`: production hard-ceiling full close 和 trajectory export。
- Deferred to `v0.19+`: Campaign matrix/admission/retry/atomic summary、第二资源类型、durable recovery 和 upstream verification。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| v0.15 Docker multi-profile visibility | `baseline-verified` | Specs 13–14 | 执行容器内 executor 与 visibility matrix | actual L1 facts、trajectory、clean evaluator 通过 | 回收 Attempt resources |
| Docker/PostgreSQL image/service | `external-accepted` | User Docker daemon + repository-pinned image digest | 按 repo Compose/Provider setup 拉取/构建固定 digest，不使用漂移 `latest` | health、network scope、schema seed、mutation/readback 和 teardown probe | 删本 Attempt container/network/volume，不改全局 Docker config |
| Environment Manager close | `phase-produced` | Agent / Phase 0–1 | 通过 production composition 创建 resource owner/action authority/effect writer | unauthorized action 零 mutation，timeout/cancel cleanup 有界 | owner inventory 为空或 non-reusable warning |
| Composed Harness mechanism package | `phase-produced` | Agent / Phase 2；`examples/l1/orchestration-environment/` | package `lib/` 定义 role/handoff 与 DB Tool mapping，同 package 提供 success 与 `environment-action-denied` task | Core 无 role/task 分支；两 profile + action + evaluator 通过；denial 零 mutation | Harness 无额外 host resource；Attempt cleanup 统一处理；tracked package 保留 |

</details>

### Runnable Acceptance

- Success smoke: `uv run bora run examples/l1/orchestration-environment --task orchestration-environment`，使用至少两 profile 和一个 PostgreSQL action。
- Expected failure: `environment-action-denied` 在 mutation 前拒绝未申明 action，数据库状态无变化且后续 invoke 计数不增加。
- Regression smokes: v0.13 trajectory、v0.14 required three-backend/mixed-profile（及可用时的 `claude-code` residual）、v0.15 visibility/writer 与旧 Environment tests。
- Observable evidence: per-profile invocation trees、effect authorize/deny、resource identity/state digest、evaluator raw/result、teardown outcome。

### Extension Seams

- `EnvironmentAdapter`: 按资源协议变化；本版实现 PostgreSQL，不为假想第二资源预建 marketplace。
- Package `lib/`: 拥有角色顺序和 handoff 数据，可被 upstream framework 替换，不上升 Core authority。

## Design

> Inherited design: [Environment Manager](../../docs/design/05-runtime-core.md#85-environment-manager)、[Agent Service](../../docs/design/05-runtime-core.md#843-agent-serviceruntime)、[带 lifecycle component](../../docs/design/06-capability-adapter-visibility.md#94-带-lifecycle-的-component)、[Evaluator barrier](../../docs/design/07-budget-evaluation-failure.md#143-evaluator-barrier)
>
> Local delta: 把已有 PostgreSQL 切片接入 Docker Attempt 的 multi-profile production path，冻结 effect evidence 和 cleanup 语义。

### Control and Data Flow

```text
package Harness
  → ctx.agent.invoke(profile A) → trajectory A
  → package-local handoff
  → ctx.environment.action(logical action)
      → Runtime allowlist/ceiling decision → effects.jsonl
      → postgresql Adapter mutation/observation
  → ctx.agent.invoke(profile B) → trajectory B
  → declared output → writer barrier
  → allowlisted resource/artifact materialization → independent evaluator
  → teardown → cleanup outcome
```

### Failure Semantics

- prepare/health 失败时 Harness 零启动；action denial 在 mutation 前产生 stable kind 与 effect record。
- Harness/Agent crash、timeout 或 cancel 都关闭 capability，终止 writers，保留 partial trajectory/effects，再 teardown resource。
- teardown 失败不修改已形成 evaluation，但资源标记 non-reusable；resource 终态未固定时 evaluator 按合同 fail closed。

## Phase 0: Resource lifecycle 与 effect property probes

### Goal

在组合 Harness 前证明 Docker PostgreSQL prepare/action/teardown、credential/network visibility、deny-before-mutation 和 cancel cleanup。

### Tasks

- 冻结 image digest、schema seed、health/readback 和资源 owner identity，执行 clean/repeated/partial prepare。
- 用 sentinel action 证明 allow/deny 与 `count_on=authorized`计数点，拒绝时零 DB mutation。
- 测试 timeout/cancel/crash 下 writer/effect 收口、teardown 与资源不可复用标记。

### Files

- `src/bora/environment/manager.py`
- `src/bora/adapters/environment_postgres.py`
- `tests/environment/test_postgres_lifecycle_probe.py`
- `tests/environment/test_action_pre_effect_denial.py`
- `tests/environment/test_environment_cancel_cleanup.py`

### Acceptance Criteria

- [ ] Fixed image/resource 可重复 prepare/health/action/teardown，不可用时 Harness 零启动。
- [ ] Unauthorized action 零 mutation，effect record 不含 credential/DSN password。
- [ ] Cancel/crash 有界清理，`R1`–`R2` 关闭后才进 Phase 1。

## Phase 1: Environment Manager/Capability production close

### Goal

将 lifecycle、action authority、resource projection、effect writer 和 cleanup 接入 production composition。

### Tasks

- Environment Manager 按 Attempt 创建 owner，Capability 仅接受 locked logical action/params。
- Adapter 获得 resource credential/network，Harness/Agent 仅获得已脱敏 observation。
- 在 effects 记录 authorize/deny/start/terminal，关联 Attempt/invocation 但不复制 secret。

### Files

- `src/bora/environment/manager.py`
- `src/bora/capabilities/authority.py`
- `src/bora/adapters/environment_postgres.py`
- `src/bora/application/composition.py`
- `tests/environment/test_environment_manager.py`
- `tests/security/test_environment_credential_visibility.py`

### Acceptance Criteria

- [ ] Production action 在 mutation 前经 parent authority，unknown/denied 零 Adapter 调用。
- [ ] Resource credential 不进 Harness/Agent env/workspace/lock/trajectory/effects，focused gates 通过。
- [ ] Normal/failure/cancel 路径都有界 teardown，cleanup warning 不改写 score。

## Phase 2: Package-owned multi-profile composition

### Goal

用 package workflow 组合两 profile 和 Environment action，不引入 Core workflow owner。

### Tasks

- 在 package `lib/` 实现 role order/handoff/tool mapping，Harness 只传 profile id 和 logical action。
- 关联两 invocation trajectories、effect、artifact/resource projection 和 evaluator input。
- 加入 architecture test，拒绝 Runtime 中的 role/task/benchmark/handoff/graph 分支。

### Files

- `examples/l1/orchestration-environment/`
- `tests/acceptance/test_orchestration_environment.py`
- `tests/architecture/test_orchestration_ownership.py`
- `tests/runtime/test_composed_effect_evidence.py`

### Acceptance Criteria

- [ ] 两 profile + action + declared output + evaluator + teardown 经 production CLI 通过。
- [ ] Harness 拥有顺序/handoff，Core/Adapter 无 role/Benchmark/task 业务分支。
- [ ] Trajectory/effect/evaluation/cleanup 可关联且互不替代，focused gates 通过。

## Phase 3: Public success/failure 与状态同步

### Goal

从 clean state 验证组合成功、未授权 action、resource failure/cleanup 与全部受影响回归。

### Tasks

- 执行 success、deny-before-mutation、resource unavailable、cancel/timeout 和 secret/gold scans。
- 回归 v0.13–v0.15 及旧 Environment/public paths。
- 同步 README/Architecture/AGENTS/Roadmap/Spec，保持 mechanism-only 声明。

### Files

- `tests/acceptance/test_orchestration_environment_cli.py`
- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/15-orchestration-environment-plan.md`

### Acceptance Criteria

- [ ] Success 与全部 expected failures 经 public CLI 通过，资源无泄漏或有明确 non-reusable warning。
- [ ] Frozen install、Ruff、Pyright、pytest、Docker/PostgreSQL probes、strict validator、relative links 与 `git diff --check` 通过。
- [ ] 文档不声称 Campaign 全收口、通用 Graph/Handoff、插件或 `real-benchmark-verified`。
- [ ] Version Index 仅在本 Spec 全部证据及规定审查通过后勾选。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Core 逐渐接管多角色 workflow | Architecture test 禁止 role/branch/handoff/graph authority，中间数据留 package `lib/` |
| Harness 直接拿 DB credential | Environment Capability + Adapter-only projection + env/workspace/trajectory sentinel scan |
| Denial 发生在 mutation 后 | Adapter effect 前 parent authorize，DB readback/counter 证明零变更 |
| Resource cleanup 失败被忽略 | Owner inventory + non-reusable warning + 禁止进入复用池；score 不被改写 |
| 一个 PostgreSQL journey 被扩写成全能力 | 限定资源/image/platform/executor 证据，其他资源另立版本 |

## User Acceptance

- [ ] 用户接受 Environment 在本轴收口、PostgreSQL 作为首个机制类型、package-owned orchestration 边界与 Docker 资源 E2E，并明确授权实施。
