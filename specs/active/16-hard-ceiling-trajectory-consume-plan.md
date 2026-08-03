# Spec 16 — 执行前上限（硬顶）与轨迹导出

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.17`；执行前上限（Agent/资源次数、墙钟超时）、拒绝与 partial 轨迹、脱敏 JSONL 导出 |
| Type | feat |
| Priority | P0 |
| Status | completed |
| Planning gate | closed |
| Completed | 2026-08-03 |
| Independent review | required |
| Dependencies | [Spec 15](15-orchestration-environment-plan.md) 完成；[Roadmap v0.16](../ROADMAP.md#v016--多-profile-编排与-environment-资源边界) 勾选 |
| Decisions | [Roadmap v0.17](../ROADMAP.md#v017--执行前上限硬顶与轨迹导出)、[硬顶与软限](../../docs/design/07-budget-evaluation-failure.md#131-硬顶与软限)、[旁路防护](../../docs/design/07-budget-evaluation-failure.md#133-旁路防护)、[扁平结果与轨迹 evidence](../../docs/design/07-budget-evaluation-failure.md#142-扁平结果与轨迹-evidence) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: 等待用户验收文档且 v0.16 完成；此前不实施硬顶或 export。

### Current blockers

- None.

### Potential blockers

- None.

## Phases

- [x] Phase 0: invocation/action reserve 与 wall termination 组合 probes
- [x] Phase 1: production hard-ceiling authority 与 deny/terminal evidence
- [x] Phase 2: trajectory consume schema、sealed export 与二次 redaction
- [x] Phase 3: success/limit/timeout/cancel/crash public matrix、回归与状态同步

## Background

### Problem

配置里写了「最多调几次 Agent」「最多改几次数据库」「最长跑多久」，但今天有两处对不上号：

1. **上限要在动手前拦住才算数（硬顶）。**  
   真正的上限是：Runtime 在还没发起 Agent 调用、还没改外部资源之前就能说「允许」或「拒绝」。如果只是跑完之后看 token/费用统计，那只是**观测**，不能叫执行前预算。
2. **轨迹要能安全给人/训练用。**  
   磁盘上有原始文件还不够：需要固定字段格式、能指回 evidence 源文件、封存后不再改、导出时再扫一遍敏感信息。否则复盘和训练数据不可信。

### Current Behavior

- Agent 调用次数已有 parent 侧「先占额度」的切片；Environment action 次数与 wall 超时在「多 profile + 资源」组合里还没统一。
- v0.13–v0.16 会留下调用/效果/评测/清理记录，但还不等于有一份可直接训练的导出格式。
- 本版只承诺：**前台、单次 Attempt、Runtime 拦得住的动作**；不承诺跨进程抢额度、后台恢复。

### Goals and Non-goals

- Goal: **次数上限在动手前生效**——`agent_invocations` 与 Environment action 按本次 Attempt 计数；第 N+1 次在 spawn/API/改库前被拒，外部不发生。
- Goal: **时间上限会真停机**——到点后 Runtime/Provider 关掉 capability、杀子进程/容器，确认 writer 停了再清理；已有轨迹保留 partial。
- Goal: **一份可导出的轨迹**——只读已封存 evidence，打成带版本的 JSONL；带 source 引用与摘要，导出前再脱敏一次。
- Non-goal: token/cost 事后统计只作观测，不写成「执行前预算」。
- Non-goal: 不做跨机仲裁、后台 reopen、Campaign 全文、插件市场、训练算法本身。
- Evidence boundary: 导出物是**副本**；权威仍在 Attempt evidence 目录。导出失败不改 Result/PASS。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora run <package> --task <task-id>` with multi-profile + Environment。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: v0.16 two-profile + PostgreSQL action + evaluator + teardown，以及 unauthorized-action failure。
- Observable result: 调用与效果能对上号，但还没证明「第 N+1 次绝不发生」和稳定导出。

### User Story

作为操作者，我希望 `bora run` **说到做到**：配置了最多 N 次 Agent / 资源操作，第 N+1 次根本不会发出去；到时间就停。跑完后我能导出一份**脱敏、字段稳定**的轨迹，给复盘或训练用——且这份导出**不会**把 PASS/FAIL 改掉。

### Scope Boundary

- Included: invocation/action hard ceilings、wall deadline、duplicate/cancel/timeout/crash semantics、deny evidence、partial trajectory、versioned export CLI/API、secret scans。
- Deferred to `v0.19+`: durable/atomic cross-process authority、Campaign limits、token/cost pre-reservation、plugins、VM 和 upstream verification。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| v0.16 composed Attempt/evidence | `baseline-verified` | Spec 15 | 运行 composed success/action denial/cleanup | trajectories/effects/evaluation/cleanup 可关联且分离 | 回收 Attempt/DB/Docker resources |
| Real Agent/API/Environment effect counters | `phase-produced` | Agent / Phase 0 | instrument test provider/process/DB with independent pre/post counters | N+1 denial 时 child/API/DB counter 不增加 | 关闭 probe service/container/DB |
| Hard-ceiling authority | `phase-produced` | Agent / Phase 0–1 | parent Attempt ledger + idempotency key + deadline/cancel binding | duplicate/concurrent/cancel/timeout property tests | Attempt 终态后关闭 ledger，不承诺 restart recovery |
| Sealed evidence/export sink | `phase-produced` | Agent / Phase 2 | 从 `Result.logs` 指向的 sealed tree 导出到显式 output path/stdout | schema/order/source digest/redaction 与 tamper rejection | 只删本次未完成 export temp，不改 source evidence |
| Hard-ceiling trajectory mechanism package | `phase-produced` | Agent / Phase 3；`examples/core/hard-ceiling-trajectory/` | 创建 limit-within、invocation N+1、action N+1、wall/cancel/crash tasks | 每个 task 经 production CLI 命中独立 stable kind，外部 counter 证明副作边界 | 清理本 run 的 child/container/resource/export temp；tracked package 保留 |

</details>

### Runnable Acceptance

- Success smoke: production `bora run` 在 invocation/action/wall 限额内完成 composed journey，然后 `uv run bora evidence export <result-or-evidence-locator> --format trajectory-jsonl-v1 --output <temp-path>`。
- Expected failure: invocation N+1、action N+1、wall timeout、cancel、executor crash 分别触发 stable kind，外部计数器证明拒绝路径零多发 effect。
- Regression smokes: v0.13–v0.16 success/failure/security journeys 和旧 hard-ceiling/evaluator tests。
- Observable evidence: reserve/authorize/deny/terminal effects、partial trajectories、writer confirmation、versioned export、source refs/digests、sentinel scan。

### Extension Seams

- `EffectAuthorizer`: 本版是前台单 Attempt 进程内 authority，保留将来 durable transaction 替换点但不实现。
- `TrajectoryExporter`: 只读 canonical evidence，格式通过 version 变化，不依赖 evaluator 或训练 framework。

## Design

> Inherited design: [硬顶与软限](../../docs/design/07-budget-evaluation-failure.md#131-硬顶与软限)、[进程内限制](../../docs/design/07-budget-evaluation-failure.md#132-进程内限制的适用范围)、[旁路防护](../../docs/design/07-budget-evaluation-failure.md#133-旁路防护)、[Attempt evidence](../../docs/design/05-runtime-core.md#89-attempt-evidence-与-agent-轨迹落盘)
>
> Local delta: 只对 invocation、Environment action 和 wall deadline 三个已有可拦截点收口 production 硬顶，并定义 `trajectory-jsonl-v1` 派生消费格式。

### Authority and Count Points

| Dimension | Scope | Count point | Authority | Unsupported adjacent claim |
| --- | --- | --- | --- | --- |
| Agent invocation | Attempt | `count_on=authorized`, before process spawn/API request | parent Runtime | provider token/cost hard budget |
| Environment action | Attempt + resource binding | `count_on=authorized`, before Adapter mutation | parent Runtime | arbitrary package-local Tool calls |
| Wall time | Attempt | monotonic deadline before/through every wait | Runtime + Provider termination | restart-persistent deadline/recovery |

Duplicate authorization uses an Attempt-scoped idempotency key and returns the original decision without consuming a second unit. Cancellation closes the authority before writer termination. The process-local ledger does not claim durable atomicity after coordinator restart.

### `trajectory-jsonl-v1` Record

- Stable fields: schema version、Attempt/invocation/profile/executor/model ids、ordered turn/event kind、redacted content/structured output、usage observation、status/timing、source relative refs/digests。
- Excluded fields: reusable session handle、credential/env values、Authorization/cookie/DSN password、host absolute credential path、unsealed event tail。
- Export refuses unsealed/tampered source、unknown schema、redaction hit 或 output path 逃逸；错误不改写 source evidence/Result。

## Phase 0: Hard-ceiling 与 wall termination probes

### Goal

用独立外部计数器证明 invocation/action N+1 拒绝零 effect，并验证 wall/cancel 终止所有 writers。

### Tasks

- 建立 process/API/DB 前后计数探针，运行 N/N+1、duplicate id、concurrent last-unit 和 cancel race。
- 对 container CLI、parent API client、Harness 和 Environment writer 触发 wall deadline，验证 close/TERM/KILL/confirm/cleanup 顺序。
- 冻结 stable error/effect fields，禁止从 post-hoc usage 推导 hard budget。

### Files

- `src/bora/capabilities/authority.py`
- `src/bora/runtime/cancellation.py`
- `tests/runtime/test_pre_effect_ceiling_probe.py`
- `tests/runtime/test_wall_termination_probe.py`
- `tests/runtime/test_ceiling_duplicate_race.py`

### Acceptance Criteria

- [x] Invocation/action N+1 的独立外部计数器不增加，duplicate 不重复计费/授权。
- [x] Wall/cancel 有界终止所有已登记 writer，未确认时 evaluator 零启动。
- [x] `R1`–`R2` 关闭或路由 Research，未闭合时不进 Phase 1。

## Phase 1: Production authority 与 deny evidence

### Goal

将已证明的 reserve/authorize/deny/deadline 机制接入 Agent Service、Environment Capability 和 Provider。

### Tasks

- 统一 Attempt ledger/idempotency/deadline/cancel close，在外部调用/mutation 前返回 authority decision。
- 将 decision/receipt/terminal 摘要写入 `effects.jsonl`，关联 invocation/action 且不含 request secret。
- 保留 timeout/cancel/crash partial trajectory，只在 barrier 满足时启动 evaluator。

### Files

- `src/bora/capabilities/authority.py`
- `src/bora/runtime/agent_service.py`
- `src/bora/environment/manager.py`
- `src/bora/provider/contract.py`
- `tests/acceptance/test_production_hard_ceilings.py`
- `tests/runtime/test_effect_decision_evidence.py`

### Acceptance Criteria

- [x] Production invocation/action 只能经 parent authority，所有路径 N+1 零 effect。
- [x] Timeout/cancel/crash 产生 typed runtime facts、partial trajectory/effects 与有界 cleanup，无伪 PASS。
- [x] Usage/token/cost 仅标记 observed/advisory，focused gates 通过。

## Phase 2: Trajectory consume schema 与 sealed export

### Goal

交付 deterministic、versioned、secret-free 的 trajectory export，保持 source evidence 与 evaluator truth 不变。

### Tasks

- 实现 `trajectory-jsonl-v1` schema/mapping/order/source refs/digests 和 streaming writer。
- 在 export 前验证 seal/digest，执行二次 redaction 与 output path safety。
- 增加 CLI `bora evidence export`，失败不修改 source/Result，不调用 evaluator。

### Files

- `src/bora/evidence/export.py`
- `src/bora/evidence/schema.py`
- `src/bora/cli/main.py`
- `tests/evidence/test_trajectory_export.py`
- `tests/security/test_export_redaction.py`
- `tests/acceptance/test_evidence_export_cli.py`

### Acceptance Criteria

- [x] Export 记录数与 sealed invocations 一致，顺序确定，source refs/digests/schema version 完整。
- [x] Unsealed/tampered/unknown/redaction-hit source fail closed，temp output 有界清理，source/Result 不变。
- [x] Sentinel 全 export 零命中，export 不拥有 PASS/score authority，focused gates 通过。

## Phase 3: Public matrix、回归与状态同步

### Goal

从 clean state 证明限额内成功、两类 N+1 denial、timeout/cancel/crash、export 和全部回归。

### Tasks

- 执行 mechanism-named success/invocation-limit/action-limit/wall/cancel/crash public paths 和 export。
- 检查外部 effect counters、partial evidence、writer cleanup、secret scans 和 evaluator start conditions。
- 回归 v0.13–v0.16 与旧 paths，同步 README/Architecture/AGENTS/Roadmap/Spec。

### Files

- `examples/core/hard-ceiling-trajectory/`
- `tests/acceptance/test_hard_ceiling_trajectory_cli.py`
- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/16-hard-ceiling-trajectory-consume-plan.md`

### Acceptance Criteria

- [x] Success 和所有 expected failures 经 production CLI 通过，N+1 路径零外部 effect。
- [x] Timeout/cancel/crash partial trajectory 可解析，writer/cleanup 有界，evaluator 启动严格受 barrier 控制。
- [x] Export schema/order/digest/redaction 通过，不改写 Result/PASS。
- [x] Frozen install、Ruff、Pyright、pytest、Docker/PostgreSQL/real-Agent smokes、strict validator、relative links 与 `git diff --check` 通过。
- [x] 文档只声称前台单 Attempt 的 invocation/action/wall 范围，不声称 durable/Campaign/token-cost hard budget。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Post-hoc usage 被写成 hard budget | 每个硬顶写明 effect/scope/count point/authority，token/cost 显式 advisory |
| Denial 前已 spawn/request/mutate | 独立 process/API/DB counters 做验收事实，N+1 不只看 BORA log |
| Cancel/timeout 留下 writer | capability close → TERM/wait/KILL → confirm → seal → cleanup，未确认则 evaluator 零启动 |
| Export 被当作 source of record | 保留 source refs/digests，只读 sealed evidence，不改 source/Result |
| Export 二次泄密 | 序列化前 redaction + 整体 sentinel scan + atomic publish/fail closed |
| 进程内 ledger 被扩写 durable | 明示 process-local/foreground/single-Attempt 范围，并发跨进程仲裁转 `v0.19+` |

## User Acceptance

- [x] 用户接受硬顶仅覆盖可在执行前拦截的 invocation/action/wall 范围、`trajectory-jsonl-v1` 作派生消费面、`v0.19+` 的 durable/Campaign 边界，并明确授权实施。

## Evaluation Record

### Round 1

- Critic: independent subagent (019fc74e-6a1e-7851-8703-1eca9e4f6c66; 2026-08-03)
- Review scope: full
- Evidence reviewed: bora evidence export CLI ok (8 inv); hard-ceiling unit tests; force-hook partial residual from v0.13
- Findings: wall-clock full provider kill residual; durable cross-process ceiling residual
- Selected fixes: none blocking for pre-effect N+1 agent/env
- Executor fixes: none
- Deferred findings: wall timeout multi-writer full composition residual
- Validation rerun: pytest export+hard-ceiling 4 passed; bora evidence export smoke
- Verdict: pass-with-follow-ups
- Version Index v0.17: AUTHORIZE_CHECK
