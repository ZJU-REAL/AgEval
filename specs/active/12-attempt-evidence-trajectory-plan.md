# Spec 12 — Attempt Evidence 与 Agent 轨迹落盘

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.13`；Attempt evidence root、per-invocation trajectory、redaction、partial failure evidence 与 `Result.logs` |
| Type | feat |
| Priority | P0 |
| Status | in-progress |
| Planning gate | review（待用户验收；implementation not started） |
| Completed | pending |
| Independent review | off |
| Dependencies | 已验证的前台 `bora run` + Codex Agent Service 基线 |
| Decisions | [Roadmap v0.13](../ROADMAP.md#v013--attempt-evidence-与-agent-轨迹落盘)、[Agent Service](../../docs/design/05-runtime-core.md#843-agent-serviceruntime)、[Attempt evidence](../../docs/design/05-runtime-core.md#89-attempt-evidence-与-agent-轨迹落盘)、[产品红线](../../docs/design/00-overview-and-product.md#02-红线) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `no` |
| User decision required | `yes` |
| Ready for acceptance now | `yes` |
| Current blockers | `1` |
| Potential blockers | `1` |

- Next action: 等待用户验收 v0.13+ Roadmap 与 Specs；验收前不实施。

### Current blockers

- `B1` (Owner: User): 本轮只授权规划文档；用户尚未接受这组文档为实施基线。

### Potential blockers

- `R1` (Owner: Agent / Phase 0): 现有 Codex Adapter 能否在不依赖 stdout 作唯一事实源的前提下，稳定收集 backend event/session artifact 尚需真实 probe。

## Phases

- [ ] Phase 0: 现有 Codex 轨迹源、原子写入与 redaction 最小 probe
- [ ] Phase 1: Attempt evidence store 与 §8.9 目录合同
- [ ] Phase 2: Agent Service/Codex 热路径、partial failure 与 Result locator
- [ ] Phase 3: mechanism public smokes、回归、门禁与状态同步

## Background

### Problem

现在 `bora run` 能给出 PASS/FAIL 和一些运行目录，但**每次真正调 Agent 时说了什么、中间事件、用量**没有按固定规矩落盘。  
结果是：多轮调用谁先谁后、哪一步挂了、模型回了什么，只能靠猜或翻 stdout——没法正经复盘，更谈不上拿去训练。

### Current Behavior

- Codex 已能经 parent Agent Service 真实调用；评测结果与清理结果是分开的。
- 还**不能**声称每次调用都满足 design §8.9 的目录与字段；stdout/stderr 只够排障，不够当轨迹。
- 文档或空 schema 不算证据。

### Goals and Non-goals

- Goal: **每次 Agent 调用都有自己的目录**；成功、失败、超时、取消都写清状态与时间。
- Goal: 目录里能看到：请求摘要、后端事件流、最终回复、用量与耗时（有就写，来源标明）。
- Goal: 写盘前去掉密钥类敏感信息；扫到敏感内容就**拒绝当成功轨迹**（fail closed）。
- Non-goal: 本版不接 `pi` / `opencode` / `claude-code`，不做插件、Campaign、大盘或训练代码。
- Non-goal: 轨迹**不是**打分依据；有轨迹 ≠ PASS，缺轨迹也不由 evaluator 偷偷补 PASS。
- Evidence boundary: 只用 production `bora run` + 真实 Codex 多轮调用（含失败路径）证明；不扩写成「全后端 / 全隔离 / 真 benchmark」。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora run examples/core/sdk-agent-session --task sdk-agent-session`。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: 真实 Codex multi-invoke、`examples/core/evaluator-negative` 与旧 L0/L1 acceptance suites。
- Observable result: 已有独立评测/清理事实；**按调用落盘的轨迹合同尚未验收**。

### User Story

作为操作者，我跑完一次 `bora run` 后，能在 evidence 目录里**按调用顺序打开每一次 Agent 调用**（请求、事件、最终回复），用来复盘或准备训练数据——同时清楚：**这些文件不决定 PASS/FAIL**，打分仍只看独立 evaluator。

### Scope Boundary

- Included: Attempt-owned store、per-invocation layout、Codex collection、redaction、partial terminal evidence、`effects.jsonl` 骨架、`Result.logs`、正负 public smokes。
- Deferred to `v0.14`: 其它 built-in executors 与 capability matrix。
- Deferred to `v0.15`: Docker evidence volume、Agent 运行位置与物理可见性。
- Deferred to `v0.17`: 版本化 trajectory export/consume 合同。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| 现有 Codex public multi-invoke | `baseline-verified` | Spec 06 / 现有 acceptance evidence | `uv sync --frozen --all-packages` 后运行 baseline smoke | 两次真实 invoke + independent evaluator；offline stub 不 PASS | 沿用 Attempt process cleanup；仅清理本次 `.bora` 运行目录 |
| Codex 真实 account/network | `external-accepted` | User-owned host login/service | 复用已接受的 Codex locator，不复制 credential | preflight 只返回 available/unavailable，不打印值；不可用时 typed fail | 不修改 host credential；终止本次 child/session |
| Evidence writer/schema/redactor | `phase-produced` | Agent / Phase 0–1 | 由 production composition 创建 Attempt temp root、原子 rename/seal | crash-window、concurrency-order、sentinel 和 schema probes | 只删本 Attempt 的 unsealed temp files；sealed evidence 由 run owner 保留 |
| Backend raw/session artifacts | `phase-produced` | Agent / Phase 0–2 | Adapter 通过可验证 `collect_file`/`collect_dir`/事件流或等价能力收集 | 原始材料 ref/digest 存在；stdout 不是唯一轨迹事实 | 收集完成后关闭 handle，不删 host 非 BORA-owned session source |
| Trajectory mechanism package | `phase-produced` | Agent / Phase 3；`examples/core/attempt-trajectory/` | 创建 multi-invoke success 与可选择触发 executor crash/timeout/cancel 的 package tasks，只经 public CLI 组装 | success 可解析全 invocation 树；三条 failure task 各产生 typed partial evidence，无伪 final response/PASS | 清理本 run 的 child/workspace/unsealed temp；tracked package 保留 |

</details>

### Runnable Acceptance

- Success smoke: `uv run bora run examples/core/attempt-trajectory --task attempt-trajectory`，然后由 acceptance test 从 `Result.logs` 解析全 invocation 树。
- Expected failure: 同一 `examples/core/attempt-trajectory/` 中的 executor crash/timeout/cancel 机制 task 使第二次 invoke 中断，验证 partial evidence 与无伪 PASS。
- Regression smokes: 只运行现有 evaluator-negative、当前 invocation-limit behavior（若已有 acceptance suite）、L1 secret redaction 与 provider barrier suites；完整 production hard-ceiling closure 属于 Spec 16 / v0.17，不是 v0.13 gate。
- Observable evidence: §8.9 完整 logical tree、per-file schema/digest、redaction scan 结果、Result locator。

### Extension Seams

- `TrajectoryEventSource`: 每个 executor 可提供 backend-specific event，store 只固定 envelope、order、redaction 和 seal。
- `EvidenceSink`: 本版实现 filesystem，保留可替换边界，不预建 remote artifact store。

## Design

> Inherited design: [§8.9.1 产品要求](../../docs/design/05-runtime-core.md#891-产品要求)、[§8.9.3 目录契约](../../docs/design/05-runtime-core.md#893-最小目录契约logical-layout)、[§8.9.4 最小字段](../../docs/design/05-runtime-core.md#894-每条-agent-invocation-最小字段)、[§8.9.5 所有权](../../docs/design/05-runtime-core.md#895-所有权与非目标)
>
> Local delta: 冻结 filesystem 路径、写入顺序、终态与 redaction 失败语义，并把现有 Codex 路径接入。

### Logical Layout Contract

```text
.bora/runs/<run-or-attempt-id>/
├── summary.json
├── lock.json
├── agent/
│   ├── events.jsonl
│   └── invocations/
│       └── <nnnn>-<invocation-id>/
│           ├── metadata.json
│           ├── request.json
│           ├── events.jsonl
│           ├── final-response.json
│           └── stderr.txt
├── effects.jsonl
├── evaluation/
├── harness/
└── cleanup.json
```

`metadata.json` 至少含 `invocation_id`、Attempt id、`profile_id`、executor kind、model、started/finished、status、latency 和 event schema/version。`request.json` 是已脱敏 messages/schema/tool specs 摘要。`events.jsonl` 追加写入有序事件；若后端无 stream，仍写 lifecycle/terminal event。`final-response.json` 只在归一化结果存在时生成，包含 content、structured output、usage 和不可复用的 session 摘要。

### Failure and Redaction Semantics

- invocation 目录在外部调用前创建；metadata 先写 `running`，终态以原子替换收口。
- `events.jsonl` 保持 append-only；单行必须完整 JSON，crash 后丢弃未完整尾行但不改写既有行。
- secret、Authorization/Bearer、cookie、DSN password、host credential path 与注册 sentinel 在序列化前替换；扫描命中时封存失败并产生 sanitized typed error。
- Agent Service 拥有 invocation evidence，Runtime effect gate 拥有 `effects.jsonl`，Evaluation Core 拥有 evaluator raw/binding，Harness events 不可替代前三者。

## Phase 0: Codex 轨迹源、原子写入与 redaction probe

### Goal

在实现 store 前用真实 Codex invocation 证明可收集原始/session artifact 或等价事件源，并冻结 crash-safe append 与 redaction 策略。

### Tasks

- 盘点 Adapter 真实输出、session files/directories、events 与 stdout/stderr 的所有权，建立 source/digest 表。
- 执行真实 multi-invoke、crash-tail、重复 id、并发序号和 sentinel 脱敏 probe。
- 若无法收集可复盘材料，停止下游实施并路由 Research；不以 stdout-only 替代。

### Files

- `src/bora/adapters/agent_codex.py`
- `src/bora/runtime/agent_service.py`
- `tests/runtime/test_trajectory_source_probe.py`
- `tests/security/test_trajectory_redaction.py`

### Acceptance Criteria

- [ ] 真实 Codex 源能被稳定定位、收集和 digest，stdout/stderr 只是独立诊断文件。
- [ ] append/crash 策略保证所有已承诺 JSONL 行可解析，invocation 目录序号不冲突。
- [ ] 随机 sentinel 经 request、env、stderr 和 backend event 进入后，持久化输出零明文命中。
- [ ] Focused Ruff、Pyright、pytest 与 real probe 通过，`R1` 关闭后才进入 Phase 1。

## Phase 1: Attempt evidence store 与目录合同

### Goal

实现 Attempt-owned filesystem store、schema、写入/seal API 和 `effects.jsonl` 骨架。

### Tasks

- 实现 root/invocation allocation、safe relative path、append、atomic JSON replace、seal 和 locator。
- 实现 request/event/response redaction 与全树扫描；禁止 secret 值与 host credential path。
- 为 success/failure/cancel/crash 建立 schema/ordering/idempotency tests。

### Files

- `src/bora/evidence/__init__.py`
- `src/bora/evidence/store.py`
- `src/bora/evidence/redaction.py`
- `src/bora/evidence/schema.py`
- `tests/evidence/test_attempt_store.py`
- `tests/evidence/test_invocation_layout.py`

### Acceptance Criteria

- [ ] 目录与字段完整实现 §8.9 合同，所有 path 绑定 Attempt 且拒绝 traversal/symlink escape。
- [ ] success/failure/cancel/crash 都留下可解析 metadata/events，重复 terminal 不改写已 seal 事实。
- [ ] redaction 扫描命中时不发布未脱敏文件，错误本身不包含 secret。
- [ ] Phase 1 focused validation 通过。

## Phase 2: Agent Service/Codex 热路径与 Result locator

### Goal

将 store 接入 production Agent Service，保证返回 `AgentResult` 前已完成当次轨迹终态写入。

### Tasks

- invoke 前分配 identity/request，流式写 event，结果/异常/cancel 进入对应 terminal status。
- 收集 Codex raw/session artifact refs 与归一化 response，不保存可复用 session secret。
- 让 binder 将 Attempt root 写入 `Result.logs`，不改写 evaluation score/status。

### Files

- `src/bora/runtime/agent_service.py`
- `src/bora/adapters/agent_codex.py`
- `src/bora/evaluation/result_binding.py`
- `src/bora/application/composition.py`
- `tests/runtime/test_agent_service_trajectory.py`
- `tests/runtime/test_partial_trajectory.py`

### Acceptance Criteria

- [ ] 每个 parent-bound invoke 恰好对应一个目录，返回前 metadata 已终态化。
- [ ] Executor crash/timeout/cancel 不丢 invocation identity/events，不生成伪 final response/evaluation。
- [ ] `Result.logs` 只是 locator，Harness terminal、runtime outcome、evaluation 和 cleanup 语义无回归。
- [ ] Phase 2 focused validation 通过。

## Phase 3: Public smokes、回归与状态同步

### Goal

用 production CLI 完成轨迹 success/security/failure 验收，并同步状态文档。

### Tasks

- 增加 mechanism-named acceptance package/tests，不使用 Benchmark 或业务名命名 Adapter。
- 执行真实 Codex multi-invoke、typed failure、sentinel scan 和旧 public regressions。
- 同步 README、Architecture、Roadmap、AGENTS 当前事实；仅在证据满足时勾选。

### Files

- `examples/core/attempt-trajectory/`
- `tests/acceptance/test_attempt_trajectory_cli.py`
- `tests/security/test_attempt_trajectory_no_secret.py`
- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/12-attempt-evidence-trajectory-plan.md`

### Acceptance Criteria

- [ ] Success/expected-failure/security/regression smokes 在 clean temporary state 通过，且输出包含可定位的非敏感 evidence root。
- [ ] Frozen install、Ruff、Pyright、pytest、strict validator、相对链接与 `git diff --check` 通过。
- [ ] 文档只声称 Codex production path 已验证的 trajectory scope，不声称多后端、全面 `isolated` 或 `real-benchmark-verified`。
- [ ] 所有 Phase/AC 与实际证据同步，完成前不勾 Version Index。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| stdout 被当成原始轨迹 | Phase 0 必须证明 backend event/session artifact 收集或等价能力；stdout 仅单独存诊断 |
| redaction 破坏可复盘性 | 保留 event type/order/digest 和明确 `[REDACTED:<class>]`，不默默删行 |
| crash 留下无法解析尾部 | append-only 完整行 + terminal atomic replace + recovery parser 丢弃未完整尾行 |
| 轨迹被 evaluator 误用为 PASS | 持久化 owner 和 result binding 分层；evaluator 默认不获得整棵 trajectory |
| 文档验收被当成实施授权 | Decision Summary 保持 `Agent can continue: no`，用户验收前不修改 production code |

## User Acceptance

- [ ] 用户接受本 Spec 的 §8.9 实施边界、redaction 失败语义、Codex 真实 probe 和后续版本分配，并明确授权实施。
