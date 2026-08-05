# Spec 20 — Database suite 布局与本地 task resolve

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-05 |
| Scope | Database 根 `bora.yaml` + `tasks/*/task.yaml` 双 schema；本地 resolve；CLI `--task` 适配；仓内 examples 一次性迁移 |
| Type | feat |
| Priority | P0 |
| Status | in-progress |
| Completed | pending |
| Independent review | off |
| Planning gate | **closed for product decisions**（2026-08-05）；**实现 gate open** — 待用户显式授权改 design/`src/` |
| Dependencies | [Constitution multi-task Database](../constitution/2026-08-05-multi-task-database-package.md) accepted；无代码前置；**阻塞** [Spec 21](21-database-registry-plan.md)、[Spec 22](22-database-suite-run-plan.md) |
| Decisions | [Constitution](../constitution/2026-08-05-multi-task-database-package.md#final-decision)、[Issue #10](https://github.com/ffy6511/BORA/issues/10)、[Issue #9](https://github.com/ffy6511/BORA/issues/9)、[design 02 待同步](../../docs/design/02-task-package-and-config.md) |
| Related issues | [#9 epic](https://github.com/ffy6511/BORA/issues/9) · [#10](https://github.com/ffy6511/BORA/issues/10) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `no` |
| User decision required | `no` |
| Ready for acceptance now | `no` |
| Current blockers | `1` |
| Potential blockers | `1` |

- Next action: **等待用户显式授权实现**；授权后 Phase 0 同步 `docs/design/02`，再改 Config/CLI/examples。产品决策已于 2026-08-05 对齐。

### Current blockers

- `B1` (Owner: User): 产品决策已接受，但 **尚未授权** 改 design / production 源码；授权前 Agent 不实施。

### Potential blockers

- `R1` (Owner: Agent / Phase 3): 仓内 examples 一次性迁移后的 smoke/Skills 路径全量更新——实施期以回归清单关闭。

## Phases

- [ ] Phase 0: 设计权威同步（`docs/design/02`、glossary/overview 交付单元表述、Architecture 配置输入面）
- [ ] Phase 1: DatabaseManifest + resolve + task.yaml `load_and_lock` + fail-closed 枚举
- [ ] Phase 2: CLI `lock|run` 适配 Database 根 + 列举 tasks；错误 id 非 0
- [ ] Phase 3: 仓内 examples/fixtures **一次性**迁移 + 公开 smoke 路径更新
- [ ] Phase 4: 工程门禁、Skills/README/Architecture Current 同步、状态收口

## Background

### Problem

今日每个可运行单元是「根目录 `bora.yaml` 单 task 包」。无法表达 multi-task suite，registry 也缺少稳定的整包 identity 挂载点。Issue #10 要求先定 **文件边界与本地解析**，不实现 registry、不做全量并发。

### Current Behavior

- Config Core 读 package 根 `bora.yaml`（`format: bora.task/1`），校验 `--task` == `task_id`。
- `examples/**` 全部为单 task 根布局。
- 无 `DatabaseManifest`、无 `tasks/` 成员约定。

### Goals and Non-goals

- Goal: 规范布局 Database 根 + `tasks/<id>/task.yaml`；本地 `resolve(database, task_id)` 后复用现有 lock/run 语义。
- Goal: CLI 以 **Database 根** 为 path 参数；`--task` 选择成员。
- Goal: 仓内 examples **一次性**迁完：按 Constitution **Examples 验收布局**，`examples/core`、`examples/journeys`、`examples/l1` **各一个 Database**；原叶子 package 变为 `tasks/<task_id>/`；删除「task 根 bora.yaml 为权威」路径。
- Goal: 为 Spec 21 预留 digest 输入面（canonical 成员树枚举），**不**实现 publish。
- Non-goal: publish/pull、suite 并发、Harbor 外置 digest 清单、suite 级 PASS。
- Non-goal: 勾选 Roadmap Version Index（本 epic 用户要求暂不写 Roadmap）。
- Non-goal: 把每个今日 package 各自做成独立 Database 根（**否决**；一级目录才是 Database）。

### Key Insight

把「配置文件名」与「schema」拆开：`bora.yaml` 只表示 Database 外壳；执行真相仍在每个成员的 `task.yaml`。resolve 是薄适配，不把 suite 语义塞进 evaluator。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora lock <package> --task <task-id>` / `uv run bora run …`（当前 package = 单 task 根）。
- Production composition root: `src/bora/application/composition.py`；Config：`src/bora/config/load_and_lock.py`。
- Baseline smoke: `uv run bora lock examples/core/config-minimal --task config-minimal`；`uv run bora run examples/core/sdk-agent-session --task sdk-agent-session`（或仓库当时文档冻结命令）。
- Observable result: 单 task lock/run 可用；无 Database 布局。

### User Story

作为 BORA 操作者，我可以在本地打开一个含多个 task 的 Database 目录，用 `--task` 锁定或运行其中一题，并在错误 task id 时得到明确非 0 失败；作为维护者，仓内 examples 全部使用同一布局，不再维护第二套单包权威。

### Scope Boundary

- Included: design 同步；`bora.database/1` schema（含 `database_id` 字符集与 `defaults` 白名单）；`task.yaml` 加载；resolve；枚举；CLI 适配；**examples 三 Database 迁移**（core / journeys / l1）；digest 输入面（枚举 + 路径列表，算法可 stub）。
- Deferred: [Spec 21](21-database-registry-plan.md) publish/cache；[Spec 22](22-database-suite-run-plan.md) 全量并发与「无 `--task` 跑全员」；外置 task pin 清单。
- Compatibility: **无长期 dual-read**（Constitution D4）。
- **Examples 目标布局（验收冻结）：** 见 [Constitution D4 Examples 验收布局](../constitution/2026-08-05-multi-task-database-package.md#examples-验收布局用户确认2026-08-05)。  
  - `examples/journeys` = **一个** Database，`tasks/` 下含 `terminal-jsonl-agg` 等全部 journeys 成员。  
  - 同理 `examples/core`、`examples/l1`。  
  - CLI 入口始终是 Database 根 + `--task`，不是 `examples/journeys/terminal-jsonl-agg`。
- **CLI 过渡契约（本 Spec 完成态强制，直至 Spec 22 completed）：**  
  - `bora lock|run <database>` **必须**提供 `--task <id>`；缺省 → typed usage/config error（exit ≠ 0）。  
  - 即使 Database **只有一个成员**，也**不**自动推断 task id（保持 CLI 对称，避免双语义）。  
  - Spec 22 落地后：无 `--task` 才表示全量 suite；本 Spec 验收命令一律带 `--task`。

### Prerequisite Audit Details

<details>
<summary>Expand prerequisite sources, setup, verification, and cleanup</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Existing Config/CLI lock-run baseline | `baseline-verified` | Spec 00–18 public paths | `uv sync --frozen`；跑现有 config-minimal lock 与至少一条 L0 run | exit 0 + digest/Result 可观察 | 删除测试产生的 `.bora/runs` temp state |
| Constitution accepted | `external-accepted` | User | 用户审查通过 Constitution + 本 Spec | Status 从 draft → active；本 Spec Planning gate closed；无未授权 source edit | 决策文件不创建运行资源 |
| Design 02 交付单元改写 | `phase-produced` | Agent / Phase 0 | 编辑 `docs/design/02` 等 | 文档描述与 layout 一致；相对链接有效 | 文档变更无后台进程；git 可回滚 |
| Three public Databases under examples/ | `phase-produced` | Agent / Phase 3 | 将 `examples/{core,journeys,l1}` 各建成 Database：`bora.yaml` + `tasks/<原目录名>/` | 见 Runnable Acceptance 冻结命令；`list_tasks` 成员数与今日叶子包一致 | 删除运行产生的 `.bora/runs` temp |
| Full path/doc migration | `phase-produced` | Agent / Phase 3 | 更新 tests、Skills、README、acceptance 中所有旧 `examples/<area>/<pkg>` CLI 用法 | grep 无「CLI 指向叶子 package 根」的权威文档；pytest 绿 | 旧叶子路径仅作历史 git；工作区无双布局 |

</details>

### Runnable Acceptance

- Public entrypoint: `uv run bora lock|run <database-root> --task <task_id>`；列举：`uv run bora tasks <database-root>`（Constitution D6.10 冻结，无并列 flag 入口）。
- Success smoke（冻结命令；迁完后写入 `examples/README.md`）:

```bash
# Database = examples 一级目录；task = 原叶子包名
uv run bora lock examples/core --task config-minimal
uv run bora lock examples/journeys --task terminal-jsonl-agg
uv run bora lock examples/l1 --task sdk-session-single-actor

uv run bora run examples/core --task sdk-agent-session
# 或其它已有 L0 成功路径，task_id 为成员名

uv run bora tasks examples/journeys   # 列出 env-postgres-min、terminal-jsonl-agg 等
```

- Expected failure:

```bash
uv run bora lock examples/journeys --task does-not-exist   # exit ≠ 0，typed error
uv run bora lock examples/core                            # 缺 --task → 非 0（Spec 20 完成态）
```

- Regression smokes: 原各叶子 package 的 success/expected-failure，全部改为 `examples/<area> --task <task_id>` 后仍通过。
- Observable evidence: lock summary 含 `database_id` + `task_id`；三 Database 根均存在 `bora.yaml`（`bora.database/1`）；无叶子级权威 `bora.yaml`（task schema）；无伪 PASS；无 secret 进入 lock。

### Extension Seams

- Database path vs registry ref：resolve 输出统一为本地 `database_root`，Spec 21 只替换「如何得到 root」。
- Suite 全量调度：Spec 22 消费同一成员枚举 API，本 Spec 只保证单 task 路径。

## Design

> Inherited design: [02 Task Package](../../docs/design/02-task-package-and-config.md)（Phase 0 将「交付单元」改为 Database）；[Constitution Final Decision](../constitution/2026-08-05-multi-task-database-package.md#final-decision)
>
> Local delta: `DatabaseManifest`、`resolve_task`、task.yaml 读路径、examples 布局迁移；不实现 registry/suite scheduler。

### Control Flow

```text
CLI path = database_root
  → load_database_manifest(root)  # bora.yaml format=bora.database/1
  → resolve_task(root, task_id)   # tasks/<id>/ + task.yaml
  → load_and_lock(task_dir, task_id, …)  # 读 task.yaml
  → 既有 lock summary / run lifecycle
```

### Data Flow

- 输入：Database 根路径、`task_id`、optional overrides。
- 输出：`LockedTaskConfig`（语义同今日）+ 溯源字段（database_id、version、成员相对路径）。
- digest 预留：canonical 有序列表（成员路径 + 文件摘要输入），完整 suite digest 算法可在 Spec 21 钉死；本 Spec 至少稳定枚举顺序。

### Reference Data Structures

```text
DatabaseManifest:
  format: "bora.database/1"
  database_id: str
  version: str
  tasks_root: str          # default "tasks"
  description: str | None
  defaults: DatabaseDefaults | None

ResolvedTask:
  database_root: Path
  task_id: str
  task_dir: Path           # …/tasks/<task_id>
  task_config_path: Path   # …/task.yaml
  database_id: str
  database_version: str
```

### Core Functions and Interfaces

- `load_database_manifest(root) -> DatabaseManifest`
- `list_tasks(root) -> list[str]`（fail closed on id/dir mismatch）
- `resolve_task(root, task_id) -> ResolvedTask`
- `ConfigCore.load_and_lock`：改为从 `task.yaml` 读取（或内部 `config_filename` 参数，默认 `task.yaml`）
- CLI：package 参数语义改为 Database 根

## Phase 0: 设计权威同步

### Goal

在改代码前，使 design/Architecture 与 Constitution 一致。

### Tasks

- 改写 `docs/design/02`：交付单元 = Database；Task = 成员；废弃「task 根 bora.yaml 为唯一配置入口」为权威默认。
- 更新 glossary / overview 中 package 措辞（若冲突）。
- Architecture：标注 Config 输入为 Database resolve → task.yaml（Target）；Current 仍为单包直至 Phase 3。

### Files

- `docs/design/02-task-package-and-config.md`
- 相关 `docs/design/00` / glossary（若有）
- `ARCHITECTURE.md`（Target 段，避免把未实现标成 Current）

### Acceptance Criteria

- [ ] Design 描述与 Constitution D1–D4 一致。
- [ ] 无「双权威」残留表述。
- [ ] 文档相对链接有效。

## Phase 1: Manifest + resolve + lock

### Goal

Config 层可加载 Database 并 lock 单个成员。

### Tasks

- 实现 `DatabaseManifest` schema 与校验：  
  - `format`、`version`、`tasks.root`（wire → 内部 `tasks_root`）；  
  - **`database_id` 字符集**（Constitution D2：`^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$`，长度 1–128，禁 `..` / `//` / 首尾 `/`）；  
  - **`defaults` v1 白名单**仅 `max_concurrent_tasks`（≥1）；其它键 fail closed。  
- `list_tasks` / `resolve_task`；目录名与 `task_id` 一致性；**零成员 Database fail closed**（enumerate 或 lock 前拒绝）。
- `load_and_lock` 读 `task.yaml`；溯源字段写入 lock summary。
- 单元/acceptance：合法双 task fixture；unknown task；format 混用拒绝；非法 `database_id`；非法 `defaults` 键；缺 `--task` CLI 失败。

### Files

- `src/bora/config/*`（model、load_and_lock、errors）
- `src/bora/adapters/package_fs.py`（若需）
- `tests/…`

### Acceptance Criteria

- [ ] 无 CLI 也可通过 library 调用 resolve+lock。
- [ ] 混用 schema（根放 task 字段 / 成员放 database 字段）fail closed。
- [ ] 非法 `database_id` / 非白名单 `defaults` / 空 `tasks/` fail closed。
- [ ] 聚焦测试通过。

## Phase 2: CLI

### Goal

公开 CLI 以 Database 根工作。

### Tasks

- `bora lock|run <database> --task <id>` 接线 resolve。
- 列举 tasks：实现 `bora tasks <database>` 子命令（唯一入口）。
- 错误信息稳定、exit code 符合仓库惯例（配置错误 → 2）。

### Files

- `src/bora/cli/main.py`
- `src/bora/application/lock_command.py`、`run_command.py`

### Acceptance Criteria

- [ ] Success / expected-failure 命令可手工复现。
- [ ] `--help` 文案不再写「Task Package root 即 bora.yaml task」。

## Phase 3: Examples 一次性迁移（三 Database）

### Goal

按 Constitution **Examples 验收布局** 完成公开 examples：三个 Database 根，叶子包全部降为成员。

### Tasks

- 为 `examples/core`、`examples/journeys`、`examples/l1` 各写 Database 根 `bora.yaml`（`database_id` 固定：`example/core`、`example/journeys`、`example/l1`）。
- 将各一级目录下现有子目录 **搬入** `tasks/<dirname>/`：原 `bora.yaml` → `task.yaml`（保持 `format: bora.task/1` 与契约字段）；资产树相对 task 根不变。
- 校验：`task_id` == 目录名；`list_tasks` 计数与迁移前叶子包数一致。
- 更新 `examples/README.md`、Skills、acceptance 测试与所有文档中的 CLI 路径。
- 删除生产代码对「叶子目录 task 根 bora.yaml」的读取。

### Files

- `examples/core/**`、`examples/journeys/**`、`examples/l1/**`
- `tests/**`
- `.agents/skills/**` / `skills/**`（若引用路径）
- `examples/README.md`

### Acceptance Criteria

- [ ] 仅三处 Database 根有 `format: bora.database/1` 的 `bora.yaml`（core/journeys/l1）；成员仅有 `task.yaml`。
- [ ] `bora tasks examples/journeys` 列出全部原 journeys 包名。
- [ ] 冻结 success smoke 命令通过；缺 `--task` / 错误 task 非 0。
- [ ] 既有核心 smoke 在 `examples/<area> --task <id>` 下通过。

## Phase 4: 收口

### Goal

工程门禁与文档 Current 同步；不勾 Roadmap（本 epic 约定）。

### Tasks

- Ruff / Pyright / pytest / validate_specs_workspace。
- Architecture Current、README 状态句。
- Spec Decision Summary 更新；Constitution History 若需。

### Acceptance Criteria

- [ ] 工程门禁绿。
- [ ] `Ready for acceptance now` 可改为 `yes` 的条件已满足（用户/Critic 策略按仓规）。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 大规模 examples 迁移 diff 巨大 | Phase 3 可脚本化；保持 task 语义字段不变，只动路径 |
| Skills/文档漏改导致操作者按旧路径运行 | Phase 3 清单 + grep 旧模式 |
| digest 算法与 Spec 21 不一致 | 本 Spec 只稳定枚举顺序与路径集合；算法单一来源放 Spec 21 |

## User Acceptance

- [x] 用户接受 Constitution D1–D4：一次性迁移、无 dual-read；defaults 方案 A（仅 suite 调度键，根不写 task limits 等）（2026-08-05）。
- [x] 用户接受：Spec 20 完成态强制 `--task`；Spec 22 前无胶水推断（2026-08-05）。
- [ ] （实现后）公开 success + expected-failure 可复现。
