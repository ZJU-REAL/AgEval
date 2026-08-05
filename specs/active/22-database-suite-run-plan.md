# Spec 22 — Database suite 执行（并发 + 单 task 选择）

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-05 |
| Scope | Application 层 suite 调度：全量/单 task、Database 级并发、per-task 独立 lifecycle 与汇总；**不**实现 registry |
| Type | feat |
| Priority | P0 |
| Status | completed |
| Completed | 2026-08-05 |
| Independent review | off |
| Planning gate | **closed**；Spec 20 completed + 用户授权 |
| Dependencies | [Spec 20](20-database-suite-format-plan.md) **completed**；[Constitution multi-task Database](../constitution/2026-08-05-multi-task-database-package.md) accepted；[Spec 21](21-database-registry-plan.md) **不强制**（本地 Database 即可验收） |
| Decisions | [Constitution D5/D7/D8](../constitution/2026-08-05-multi-task-database-package.md#final-decision)、[Issue #12](https://github.com/ffy6511/BORA/issues/12)、[Issue #9](https://github.com/ffy6511/BORA/issues/9)、[Campaign 正交](../../docs/design/05-runtime-core.md)（matrix ≠ task 轴） |
| Related issues | [#12](https://github.com/ffy6511/BORA/issues/12) · [#9](https://github.com/ffy6511/BORA/issues/9) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: **用户最终验收** suite N=2 smoke。

### Current blockers

- None

### Potential blockers

- None

## Phases

- [x] Phase 0: Design 同步 suite 调度边界；冻结 CLI 标志名与 exit 策略；与 Campaign 对照表
- [x] Phase 1: Suite planner（成员列表 / 单 task 过滤）+ worker 池 + per-task 独立 run 接线
- [x] Phase 2: 汇总 summary（per-task Result 引用）+ exit code；失败策略
- [x] Phase 3: ≥3 task fixture；N=2 公开 smoke；`--task` 单跑；回归
- [x] Phase 4: 文档/Skills/Architecture；工程门禁收口

## Background

### Problem

Spec 20 提供「Database + 单 task resolve」。操作者仍需对每个 task 手敲 `bora run`。需要 **一次命令跑全部成员**，并控制 **同时跑几个 task**，同时保留 `--task` 单跑一等入口。

### Current Behavior

- `bora run` 每次一个 task（今日一个 package）。
- `bora campaign` 对**同一 task** 展开 parameter matrix，前台串行（v0.11）或后续 durable 能力；**不是** task_id 轴。

### Goals and Non-goals

- Goal: `bora run <database>` 默认跑全部成员；每 task 独立 lock + Trial/Attempt + Result/evidence。
- Goal: `--max-concurrent-tasks N`（N≥1）限制同时 in-flight task 数；Database `defaults.max_concurrent_tasks` 可作默认。
- Goal: `--task <id>` 只跑一个（与 Spec 20 同一 resolve）。
- Goal: 汇总可观察；**无 suite PASS**；单 task FAIL **默认不取消**其余。
- Non-goal: registry（Spec 21）；跨 task 默认可写共享盘；suite 级 evaluator；mid-loop handoff；把 task 扫描逻辑放进 Core Evaluation。
- Non-goal: Roadmap Version Index（epic 约定）。

### Key Insight

Suite run 是 **Application 的 task_id 轴调度**；Campaign 是 **同一 task 的 variant 轴**。两者都「多个 Trial」，但配置真相与 identity 不同——共享并发原语可以，合并语义不可以。

## Increment Contract

### Starting Runnable Baseline

- Required: Spec 20 completed。
- Public entrypoint: `bora run <database> --task <id>`（单题）。
- Production composition root: `src/bora/application/composition.py`；可参考 `campaign.py` 的串行/admission 模式。
- Baseline smoke: 多成员 Database 上分别 `--task` 跑通至少 2 题（可 mock executor）。
- Observable result: 仅单 task；无 suite summary。

### User Story

作为 BORA 操作者，我可以对一个本地 Database 执行 `bora run ./suite --max-concurrent-tasks 2`，看到每个 task 的独立结果与 evidence，并确认同时运行的 task 数不超过 2；我也可以继续用 `--task` 只跑一题。任一题 FAIL 不会抹掉其它题的 Result，也不会被解释成整个 suite PASS。

### Scope Boundary

- Included: 全量/单 task 模式；并发池；独立 workspace/Attempt；summary；exit code；≥3 task fixture；可证并发上限；与 Campaign 文档对照。
- Deferred: Spec 21 ref 上的 suite e2e（可选 follow-up）；fail-fast 模式（默认不做；若加必须显式 flag）；跨 process durable suite coordinator（属更高成熟度，非本切片）。
- Explicit local decisions（供用户批）：

| 项 | 本 Spec 冻结值 |
| --- | --- |
| CLI 并发标志 | `--max-concurrent-tasks`（整数 ≥1） |
| 缺省并发 | `1`（串行安全默认）；Database `defaults.max_concurrent_tasks` 若存在则采用，CLI 覆盖 |
| `--task` + `--max-concurrent-tasks` 同传 | **合法**：等价于单 task 运行；N 被忽略（可 warning），不报错 |
| 无 `--task` | 全量 suite（**仅本 Spec 完成后**；Spec 20 完成态仍强制 `--task`） |
| FAIL 行为 | **继续**其余 task（非 fail-fast） |
| ERROR / 基础设施失败 | 记录后继续其余；**进程 exit code 非 0** |
| 全部 PASS | exit 0 |
| 存在 FAIL 无 ERROR | exit **1**（Phase 0 对照现有单 task FAIL 码表；若现状不同则改本表与单题对齐，禁止两套） |
| 存在 ERROR | exit **2**（Phase 0 对照现有 runtime/config error 码表后冻结） |
| Admission | 每 task **独立** dry-lock/run；单成员 lock 失败 → 记 ERROR 并继续其余；**零成员**或 manifest 非法 → 立即非 0、零 Attempt |
| Summary 位置 | **Database 根下** `.bora/suite-runs/<suite_run_id>/summary.json`（Constitution D6.10；不写 cwd 相对） |
| 共享可写盘 | **禁止**默认共享；每 task 独立 Attempt workspace |

### Prerequisite Audit Details

<details>
<summary>Expand prerequisite sources, setup, verification, and cleanup</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Spec 20 list_tasks + resolve | `baseline-verified` | Spec 20 completed evidence | 使用 multi-task fixture | `bora tasks` / lock per member | 沿用 Spec 20 cleanup；删除 lock 测试 temp |
| Constitution D7 | `external-accepted` | User | 审查通过 | Status active；本 Spec Planning gate 可关 | 决策文件不创建运行资源 |
| Per-task run lifecycle | `baseline-verified` | 现有 `bora run` production path | 复用 application run 路径 | 单 task Result/evidence 可观察 | 现有 Attempt/Provider cleanup ledger |
| ≥3 task fixture（快、可 mock） | `phase-produced` | Agent / Phase 3 | 新建 suite fixture；避免强依赖真实 LLM 费用 | 全量 N=2 在 CI 可承受时间内完成 | 删除 suite 运行产生的 `.bora/suite-runs` 与 `.bora/runs` temp |
| Concurrency proof hook | `phase-produced` | Agent / Phase 1 | 测试用 harness 睡眠/文件锁 或 metrics counter | 观测 max in-flight ≤ N | 测试 teardown 释放锁/临时文件；无常驻 worker |

</details>

### Runnable Acceptance

公开 suite 入口与 Spec 20 相同 Database 根（见 Constitution Examples 布局）。全量并发验收优先用 **较快/可 mock 的子集** 或专用 fixture；完整 `examples/journeys` 全员并发可为可选加长 smoke（费用/时长敏感时 env-gated）。

```bash
# 单 task（与 Spec 20 相同形态）
uv run bora run examples/journeys --task terminal-jsonl-agg
uv run bora run examples/core --task config-minimal

# 全量 suite（本 Spec）：示例 — journeys Database，并发 2
# 若 journeys 全员过重：允许 tests/fixtures/databases/suite-min（≥3 task）作为必过 smoke，
# 但仍须证明生产 CLI 对 examples/* Database 根可无 --task 调度（至少 1 次真实 examples 路径）。
uv run bora run examples/journeys --max-concurrent-tasks 2
# 或
uv run bora run tests/fixtures/databases/suite-min --max-concurrent-tasks 2

# 期望：未知 task
uv run bora run examples/journeys --task missing   # 非 0
```

- Observable: summary 列出每 task 的 terminal verdict / Result locator；evidence 分目录；并发证明（测试或日志 metrics）；**无** suite-level PASS 字段充当权威。
- Regression: 单 `--task` 路径；Campaign 仍只做 matrix；Spec 20 lock。
- Expected failure: 非法 N（0/负数）、空 Database、成员 lock 失败时的 typed 错误。

### Extension Seams

- resolve 输入可以是 path 或（Spec 21 后）cache root——调度器只消费 `database_root + task_ids`。
- worker 池可后续被 durable coordinator 替换，但 v1 前台进程内池即可。

## Design

> Inherited: [Constitution D7](../constitution/2026-08-05-multi-task-database-package.md#d7-suite-执行issue-12)；Campaign 为 variant 轴
>
> Local delta: `SuiteRunCoordinator`（application）+ CLI 无 `--task` 时的全量模式。

### Control Flow

```text
bora run database [--task id] [--max-concurrent-tasks N]
  → load_database_manifest
  → task_ids = [id] | list_tasks(root)
  → admit: 每个 task dry-lock（推荐：启动前全员 lock 失败 → 零 Attempt 或 per-task 记录错误——Phase 1 选 **per-task fail 并继续**，与 FAIL 策略一致；admission 全失败则非 0）
  → worker pool size = N
  → for each task: resolve → run lifecycle → store Result ref
  → write suite summary → exit code
```

### Data Flow

- 每 task：独立 `LockedTaskConfig` digest、Attempt evidence 根、Result。
- Summary：仅引用与可比较字段（task_id、verdict、digests、locators）；无 credential、无 raw workspace 拷贝。

### Reference Data Structures

```text
SuitePlan:
  database_id, database_version, database_root
  task_ids: list[str]
  max_concurrent_tasks: int

SuiteSummary:
  plan_id / created_at
  tasks: [{ task_id, status, verdict, result_ref, evidence_ref, error? }]
  counts: { pass, fail, error, skipped }
```

### Core Functions and Interfaces

- `plan_suite_run(...)` / `execute_suite_run(...)`
- 复用单 task `run_command` 内核，避免复制 lifecycle
- **禁止** Core Evaluation 读取「suite PASS」

## Phase 0: 边界与标志冻结

### Goal

文档与 CLI 名称一致。

### Tasks

- design/02 或 runtime 文档增加 suite vs campaign 对照。
- 确认 exit code 与现有 `bora run` 单题一致策略。

### Acceptance Criteria

- [x] 对照表落地；无「suite PASS」措辞。

## Phase 1: Scheduler

### Goal

可并发跑多个 task。

### Tasks

- worker 池；独立 workspace；禁止默认共享可写。
- 并发上限 instrumentation。

### Acceptance Criteria

- [x] 单元/集成证明 in-flight ≤ N。
- [x] 每 task 独立 Result 路径。

## Phase 2: Summary + exit

### Goal

操作者可读汇总。

### Tasks

- atomic summary 写入。
- exit code 矩阵实现与测试。

### Acceptance Criteria

- [x] FAIL-only → 约定 exit；含 ERROR → 约定 exit；全 PASS → 0。

## Phase 3: 公开 smoke

### Goal

≥3 task、N=2、单 task 选择。

### Tasks

- fixture + README 命令。
- 回归 Campaign 与单 task。

### Acceptance Criteria

- [x] ≥3 task fixture；`--max-concurrent-tasks 2` 全量跑完；可证 in-flight ≤ 2。
- [x] 每 task 独立 Result/evidence locator 出现在 suite summary。
- [x] `--task` 只跑一个；与 `--max-concurrent-tasks` 同传不报错。
- [x] 构造单 task FAIL：其余 task 仍完成；summary 计数正确；无 suite PASS 权威字段。
- [x] 工程上无伪 PASS。

## Phase 4: 收口

### Goal

文档与门禁。

### Acceptance Criteria

- [x] Skills/README 更新；工程门禁绿；不勾 Roadmap。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 与 Campaign 概念混淆 | 文档对照表 + 不同 CLI 命令/标志 |
| 真实 LLM suite 费用/时长 | fixture 用 mock / 快速 task；真实 agent 仅可选 |
| 并发下 evidence 目录碰撞 | per-task Attempt id 命名空间 |

## User Acceptance

- [x] 用户接受：默认并发=1、CLI 覆盖、**一题 FAIL 不取消其余**、exit 0/1/2、无 suite PASS（2026-08-05）。
- [x] 用户接受：暂不更新 Roadmap / 不勾 Version Index（2026-08-05）。
- [x] （实现后）≥3 task N=2 smoke 可复现（tests + suite-min fixture；用户最终验收）。
