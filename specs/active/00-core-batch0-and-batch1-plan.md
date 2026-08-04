# Spec 00 — v0.1 BORA Core 1：Config

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-02 |
| Scope | `v0.1` Config Core；最小 Python 工程骨架；`bora lock` |
| Type | feat |
| Priority | P0 |
| Status | review |
| Completed | pending |
| Independent review | required |
| Dependencies | none |
| Decisions | [Roadmap v0.1](../ROADMAP.md#v01--bora-core-1config)、[Config Core](../../docs/design/02-task-package-and-config.md#6-core-1-详细设计config)、[Core 1 边界](../../docs/design/01-bora-core.md#23-core-1配置加载与锁定) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: 完成 Independent Critic（Evaluation Record）后，交由用户执行 User Acceptance；用户通过后勾选 Roadmap Version Index `v0.1`。

### Current blockers

- None.

### Potential blockers

- None.

## Phases

- [x] Phase 0: 可复现工程骨架、CLI 入口与 production composition root
- [x] Phase 1: Config 模型、Package 校验与 `load_and_lock`
- [x] Phase 2: `bora lock`、确定性摘要与公开正负向检查点
- [x] Phase 3: 全量门禁、证据与状态文档同步

## Background

### Problem

仓库已有自包含设计与 Specs，尚无 `pyproject.toml`、production 源码、CLI 或 composition root。操作者无法从 `bora.yaml` 得到可比较、可复盘的锁定配置，也无法在启动 Attempt 之前识别无效引用、越界路径或不支持的声明。

### Current Behavior

- Public entrypoint、production composition root 与产品 smoke 均不存在。
- 当前只有 strict Specs validator 等文档门禁；证据等级为 `design-only`。
- `bora.yaml`、`LockedTaskConfig` 与 `load_and_lock` 仅存在于设计文档，未形成实现证据。

### Goals and Non-goals

- Goal: 完整交付 Roadmap `v0.1` 的 Config Core 工程检查点，操作者可从 clean checkout 安装项目，并通过 production CLI 获得确定、无 secret 的锁定摘要或可理解的 fail-closed 错误。
- Non-goal: 本 Spec 不创建 Run / Trial / Attempt、Provider、Capability、Harness Core、Evaluator、AgentExecutor、`bora run` 或任何对应伪实现。
- Evidence boundary: 本 Spec 完成后仍保持 `design-only`；首条真实 Agent 产品路径与 `runnable-mvp` 证据由 `v0.6` 负责。

### Key Insight

`v0.1` 以 Config Core 作为完整发版与用户验收单位。`bora lock` 是可调用的工程检查点，只证明配置读取、合并、校验、canonicalize、digest 与不可变 lock；它不证明 Attempt、Agent 或 Evaluator 可运行。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: none。
- Production composition root: none。
- Baseline smoke: none；`python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict` 仅为文档门禁。
- Observable result: `design-only` 文档与 Specs 工作区。

### User Story

As a BORA operator, I can install the repository and run `bora lock` against a Task Package, so that I receive a deterministic, secret-free locked configuration summary or a fail-closed validation error before any Attempt can exist.

### Scope Boundary

- Included: 可复现 Python 工程、production CLI composition、Task Package 根目录与 `bora.yaml` 定位、配置读取与覆盖、声明/引用校验、canonical payload、SHA-256 digest、递归不可变 `LockedTaskConfig`、确定性 stdout JSON 摘要及公开负向路径。
- Deferred to `v0.2`: Run / Trial / Attempt identity、状态机与 cleanup 入口。
- Deferred to `v0.3`–`v0.5`: Provider L0、Capability API 与 Harness Core HC-1。
- Deferred to `v0.6`: 真实 Codex、独立 Evaluator、`bora run` 产品竖切与 `runnable-mvp` 证据。
- Deferred to `v0.8+`: 物理隔离、credential projection、第二 Executor、真实 Environment、Campaign 与耐久 authority。

### Prerequisite Audit Details

<details>
<summary>展开前置条件来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| `uv` 命令 | `baseline-verified` | 当前开发环境；2026-08-02 已执行 `uv --version` | 当前环境无需供应；clean checkout 先以 `uv --version` preflight，命令缺失则不进入 Phase 0 | `uv --version` 返回 `uv 0.11.26` | 不创建仓库资源 |
| CPython 3.12 供应路径 | `baseline-verified` | 当前开发环境；2026-08-02 已执行 `uv python find 3.12` | `uv python install 3.12`；Phase 0 用 `.python-version` 固定项目选择 | `uv run python -c "import sys; assert sys.version_info[:2] == (3, 12)"` | 仅移除项目 `.venv/`；不删除共享解释器缓存 |
| Frozen 依赖图与工程门禁配置 | `phase-produced` | Agent / Phase 0；`pyproject.toml`、`uv.lock`、`.python-version` | Phase 0 执行 `uv lock`，随后 `uv sync --frozen` | clean checkout 中 `uv sync --frozen` 成功；Ruff、Pyright、pytest 命令可调用 | 移除 `.venv/` 与工具缓存；tracked lock 保留 |
| Production CLI 与 composition root | `phase-produced` | Agent / Phase 0；`src/bora/cli/main.py`、`src/bora/application/composition.py` | `uv sync --frozen` 安装 `bora` console script | `uv run bora --help` 返回 0，且入口经 application composition 装配 | 无常驻进程或外部资源 |
| Config 模型、声明 catalog 与 Package 文件读取 | `phase-produced` | Agent / Phase 1；`src/bora/config/`、`src/bora/adapters/package_fs.py` | 由 Phase 1 随 production package 安装 | 单元测试证明 schema、引用、路径、override、canonicalization、digest 与不可变性；Config 不 import/execute `harness.py` 或 evaluator | 仅内存对象；无外部资源 |
| 正负向 Task Package | `phase-produced` | Agent / Phase 2；`examples/core/config-minimal/`、`examples/core/config-invalid/` | tracked example 随 clean checkout 提供 | success 与 expected-failure 命令分别返回 0 与 2；测试确认失败不生成 `.bora/` 成功产物 | example 为 tracked 文件；命令不创建 `.bora/` |

</details>

成功检查点不依赖 network、service、credential、container、Agent、Evaluator 或人工预置数据。声明 catalog 只验证 Config 所识别的 kind、format 与引用组合，不表示后续 Core 或 Adapter 已实现。

### Runnable Acceptance

- Public entrypoint: `uv run bora lock <package> --task <task-id> [--set <json-pointer>=<json-value>]`。
- Production composition root: `src/bora/application/composition.py`。
- Clean setup: `uv sync --frozen`。
- Success smoke: `uv run bora lock examples/core/config-minimal --task config-minimal` 返回 0，并只向 stdout 输出一份确定性 JSON 摘要。
- Expected failure: `uv run bora lock examples/core/config-invalid --task config-invalid` 返回 2，stderr 给出稳定错误码与可理解说明，stdout 无成功摘要，且不创建 `.bora/` 成功 lock。
- Determinism: `uv run pytest tests/acceptance/test_config_lock_cli.py -k determinism` 证明同一输入两次产生相同 canonical payload 与 digest；`--set /parameters/seed=7` 改变 digest，并在 resolution record 中记录来源与 JSON Pointer。
- Regression smokes: none；这是 greenfield 仓库的首个 production 工程检查点。
- Observable evidence: stdout JSON 至少包含 `format`、`task_id`、`resolved_references`、`resolution` 与 `digest`；字段顺序、路径表示和 digest 在相同输入下稳定，且不含 secret value、主机绝对路径或时间戳。

### Extension Seams

- `ConfigCore.load_and_lock`: 接受 `CapabilityCatalog` 协议；`v0.1` 只提供声明级 catalog，后续 composition 可注入 runtime-backed catalog，无需让 Config import Provider 或 Agent Adapter。
- Package reader: Config 依赖窄的只读 Package 文件接口；`v0.1` 只实现本地文件系统 Adapter，不引入 registry 或第二实现。
- CLI composition: Typer 与具体文件系统对象只在 application composition root 装配；Config 模型不依赖 CLI 框架。

## Design

> Inherited design: [Task Package 交付单元](../../docs/design/02-task-package-and-config.md#51-交付单元)、[`bora.yaml` 顶层结构](../../docs/design/02-task-package-and-config.md#52-borayaml-的顶层结构)、[Config 职责](../../docs/design/02-task-package-and-config.md#61-职责)、[Config Core façade](../../docs/design/02-task-package-and-config.md#64-config-core-façade)、[覆盖顺序](../../docs/design/02-task-package-and-config.md#65-覆盖顺序)、[配置校验](../../docs/design/02-task-package-and-config.md#66-配置校验)、[Target ownership 与 dependency direction](../../ARCHITECTURE.md#module-ownershiptarget)。
>
> Local delta: 冻结 `v0.1` 的 production CLI、确定性 stdout 摘要、错误边界、文件落点与测试证据。声明 catalog 只证明 Config 引用可识别；所有运行时 authority 继续由后续 Core 版本拥有。

### Control Flow

```text
operator
  → `bora lock <package> --task <id> [--set ...]`
  → CLI 解析 argv
  → application composition 注入 PackageReader + declaration CapabilityCatalog
  → ConfigCore.load_and_lock(package_root, task_id, variant=None, overrides, capabilities)
      → 定位并安全读取 `bora.yaml`
      → 合并明确 defaults 与 CLI overrides
      → 校验 schema、引用、capability 声明与 package path
      → canonicalize → digest → recursively immutable LockedTaskConfig
  → success: stdout JSON summary + exit 0
  → failure: stderr error code/message + exit 2；无成功 stdout、无 `.bora/` 产物
```

`load_and_lock` 不 import 或执行 package-local Python，不读取第二份配置，不启动 Attempt，也不调用 Provider、Agent 或 Evaluator。

### Data Flow

| Data | Source → consumer | Local constraint |
| --- | --- | --- |
| Package root、task id、repeatable `--set` | CLI → application → Config | package root 在读取前 resolve；越界与非目录输入 fail-closed |
| `bora.yaml` | PackageReader → Config | 唯一规范配置输入；safe YAML；拒绝 duplicate key、环境变量插值与第二配置文件 |
| Defaults / variant / explicit overrides | Config merge → ResolutionRecord | 顺序为 `bora.yaml → Campaign variant → explicit override`；`v0.1` 无 Campaign variant CLI，但 façade 与测试保留该输入；override 只允许已声明可覆盖 JSON Pointer |
| Capability declarations | composition catalog → Config validation | 只验证 kind/format/引用可识别；不创建或冒充 runtime capability |
| Canonical payload | resolved config + resolution → digest | UTF-8 canonical JSON；对象 key 排序、数组顺序保留、package 内路径规范化；排除主机绝对路径、时间戳与 digest 自身 |
| Lock summary | immutable lock → CLI stdout | 确定性 JSON；只含可复盘字段与逻辑引用；无 credential material |
| Config error | Config → CLI stderr | 稳定 `error_code`、JSON Pointer 或 package-relative path、可理解 message；不含 traceback 或 host secret |

### Reference Data Structures

- `LockedTaskConfig`: 覆盖 design/02 §6.3 的顶层 section，所有嵌套 mapping、sequence 与 scalar 在返回前递归冻结；lock 后修改输入 mapping 或返回对象均不能改变 canonical payload 与 digest。
- `ResolutionRecord`: 按生效顺序记录 source、JSON Pointer 与规范化值来源；至少区分 `bora.yaml`、明确 default 与 `cli-override`，不记录环境变量或 credential value。
- `CapabilityCatalog`: Config 只读协议，回答声明的 format、runtime、provider/environment/executor kind 与 output format 是否可识别；catalog 的肯定结果不构成 runtime implementation evidence。
- `LockSummary`: CLI stdout view，固定包含 `format`、`task_id`、`resolved_references`、`resolution` 与 `digest`；不默认持久化为 `.bora/` 文件。
- `ConfigError`: 至少覆盖 `invalid_package`、`invalid_format`、`unknown_task`、`unknown_profile`、`unsupported_capability`、`path_outside_package`、`unknown_package_path` 与 `invalid_override`，统一映射到 CLI exit 2。

### Core Functions and Interfaces

```python
class ConfigCore:
    def load_and_lock(
        self,
        package_root: Path,
        task_id: str,
        *,
        variant: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        capabilities: CapabilityCatalog,
    ) -> LockedTaskConfig:
        ...
```

- `variant` 保留 façade 参数与固定 merge 顺序，但 `v0.1` CLI 不暴露 Campaign variant；测试直接覆盖其合并和 resolution 语义，为 `v0.11` 留出已设计边界。
- Package 一级路径严格采用 design/02 allowlist。未知一级路径、绝对路径、`..`、解析后越出 package root 的 symlink、缺失 locator target 均在 lock 前拒绝。
- `--set` 使用 `<JSON Pointer>=<JSON value>`；Phase 1 固定可覆盖路径清单并拒绝结构替换、未知 pointer 与解析失败。所有 override 经同一 schema、引用和 capability 校验。
- SHA-256 输入为不含 `digest` 字段的 canonical locked payload；输出格式固定为 `sha256:<64 lowercase hex>`。

### Engineering Gates

- [x] `uv sync --frozen`
- [x] `uv run ruff format --check src tests`
- [x] `uv run ruff check src tests`
- [x] `uv run pyright`
- [x] `uv run pytest`（25 passed）
- [x] `python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict`
- [x] `git diff --check`

## Phase 0: 可复现工程骨架与 composition root

### Goal

从 clean checkout 可安装 BORA，并通过 production console script 到达唯一 application composition root。

### Tasks

- 建立 Python 3.12 project metadata、frozen dependency graph、`src/` package layout 与 Ruff / Pyright / pytest 配置。
- 建立 Typer console script `bora`、`bora --help` 与 `application/composition.py`；CLI 只处理 argv、输出与 exit code 映射。
- composition root 显式装配 Config use case 的依赖，不在模块导入时创建全局 Adapter 单例。
- 添加安装、import、help 与 dependency-direction 基线测试。

### Files

- `.python-version`
- `pyproject.toml`
- `uv.lock`
- `src/bora/__init__.py`
- `src/bora/cli/__init__.py`
- `src/bora/cli/main.py`
- `src/bora/application/__init__.py`
- `src/bora/application/composition.py`
- `tests/test_package_baseline.py`

### Acceptance Criteria

- [x] `uv sync --frozen` 与 `uv run bora --help` 在 clean checkout 返回 0。
- [x] `bora` console script 经 `src/bora/application/composition.py` 装配；测试 helper 不成为 production wiring。
- [x] Ruff、Pyright 与 pytest 的 Phase 0 focused gates 通过。
- [x] 临时集成缺口已由 Phase 1–2 闭合（`bora lock` 已接入）。

## Phase 1: Config 模型、Package 校验与 `load_and_lock`

### Goal

从本地 Task Package 安全产生确定、递归不可变的 `LockedTaskConfig`，所有无效输入在任何运行边界之前 fail-closed。

### Tasks

- 实现 Config model、safe YAML reader、明确 defaults、variant/override merge、ResolutionRecord、reference validation、canonicalization 与 SHA-256 digest。
- 实现 design/02 的顶层 section、Package 一级 allowlist、locator/path 约束及本 Spec 列出的错误分类。
- 实现 declaration-only `CapabilityCatalog` 协议与 composition 侧 catalog；命名与错误不得暗示 Provider、Executor 或 Environment 已可运行。
- 证明 Config 不 import/execute `harness.py`、evaluator 或 task-local library，也不读取 env 作为实验语义或第二配置来源。
- 添加 model、merge、path、reference、immutability、canonicalization、digest、secret-redaction 与失败矩阵测试。

### Files

- `src/bora/config/__init__.py`
- `src/bora/config/model.py`
- `src/bora/config/load_and_lock.py`
- `src/bora/config/errors.py`
- `src/bora/config/capabilities.py`
- `src/bora/adapters/__init__.py`
- `src/bora/adapters/package_fs.py`
- `tests/config/`

### Acceptance Criteria

- [x] 同一 package + task + variant + overrides + catalog 两次 lock 的 canonical payload 与 digest 完全相同。
- [x] 合法 override 改变目标值与 digest，并按固定顺序进入 ResolutionRecord；非法/未知 override 不产生 lock。
- [x] duplicate key、未知 profile、unsupported capability、未知一级路径、路径逃逸、缺失引用与 schema 错误均返回对应 `ConfigError`。
- [x] 测试证明输入 mapping 后续修改、返回对象 mutation 尝试和 checkout 绝对位置变化不能改变既有 lock 或 digest。
- [x] 测试证明 lock/summary 不含环境变量展开值、credential material、主机绝对路径或时间戳。
- [x] Phase 1 focused Ruff、Pyright 与 pytest 通过；CLI 与 examples 由 Phase 2 闭合。

## Phase 2: `bora lock` 与公开正负向检查点

### Goal

操作者经 production CLI 获得确定性锁定摘要，所有公开失败分支可理解、非破坏且不伪造后续阶段。

### Tasks

- 实现 application lock use case 与 CLI `lock` 子命令，冻结 argv、exit code、stdout/stderr 和 `--set` 语义。
- 创建 `config-minimal` 与 `config-invalid` Task Package；invalid fixture 固定为 unknown profile，并以单独测试覆盖其余错误类别。
- 输出确定性 JSON `LockSummary`；成功与失败均不默认创建 `.bora/`、Run、Trial、Attempt 或 evidence tree。
- 添加 public-entrypoint acceptance tests，覆盖 success、expected failure、determinism、合法 override、无产物与无 task-local import。

### Files

- `src/bora/application/lock_command.py`
- `src/bora/cli/main.py`
- `examples/core/config-minimal/bora.yaml`
- `examples/core/config-minimal/harness.py`
- `examples/core/config-invalid/bora.yaml`
- `examples/core/config-invalid/harness.py`
- `tests/acceptance/test_config_lock_cli.py`

### Acceptance Criteria

- [x] Success smoke 返回 0；stdout 只有一份可解析 JSON，字段和值满足 Runnable Acceptance。
- [x] Expected failure 返回 2；stderr 包含 `unknown_profile` 与 package-relative location，stdout 为空。
- [x] success 与 failure 后均无 `.bora/` 成功 lock、Run/Trial/Attempt、Evaluator 或伪 PASS 产物。
- [x] CLI determinism、override digest 与 no-import acceptance tests 通过；测试调用 production console entrypoint 与 composition root。
- [x] Phase 2 focused Ruff、Pyright 与 pytest 通过，Spec 级公开路径已经闭合。

## Phase 3: 全量门禁、证据与状态文档同步

### Goal

实现事实、公开命令、证据等级与权威投影一致，并形成可供用户立即复验的 `v0.1` 验收包。

### Tasks

- 从 clean temporary checkout 执行 prerequisite setup、success、expected failure、determinism、完整测试与工程门禁，记录命令、exit code、关键 stdout/stderr 和限制。
- 更新 `README.md` 的安装、`bora lock` 正负向命令、输出边界与当前支持范围。
- 更新 `ARCHITECTURE.md` Current source tree、public entrypoint、composition root、smoke 与证据等级；同步 root/specs `AGENTS.md` 当前事实。
- 按真实证据更新本 Spec Phase/验收状态与 Roadmap `v0.1` 内部清单；Version Index 保持未勾选，直到用户完成最终验收。

### Files

- `README.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `specs/AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/00-core-batch0-and-batch1-plan.md`

### Acceptance Criteria

- [x] Runnable Acceptance 的 success、expected failure、determinism 与无产物断言通过（acceptance tests + 本机 `uv run bora lock`）。
- [x] Engineering Gates 全部通过；结果见上文 Engineering Gates 勾选。
- [x] README、Architecture Current、root AGENTS 与真实文件、入口和 `design-only` 证据等级一致。
- [x] Roadmap `v0.1` 内部交付/验收勾选只反映已通过证据，Version Index 等待用户最终验收。
- [x] Spec 进入 `review`，等待 User Acceptance 与 Independent Critic；不提前 `completed`/archive。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 把 Config 声明 catalog 误读为 runtime capability | 类型、输出与 README 使用 `declaration-only` 语义；无 Provider/Agent/Environment 实现或运行入口 |
| canonicalization 受 checkout、YAML loader 或无序容器影响 | 固定 safe parser、duplicate-key 拒绝、path normalization、canonical JSON 与跨目录 determinism 测试 |
| lock/summary 泄露 credential 或环境值 | 禁止 env interpolation 与 raw credential config；摘要仅含逻辑引用；secret fixture 负向扫描 |
| package path 或 symlink 逃逸 | 读取前 resolve，所有 locator 必须位于 package root；越界在读取/导入前拒绝 |
| Config Core 膨胀成后续 Runtime | 文件与 import boundary 明确；不创建 Run、Provider、Capability、Harness、Evaluator 或 Adapter registry |
| 用户把 `bora lock` 当作产品可运行证据 | README、Architecture、Roadmap 与 CLI 摘要持续标明 Config checkpoint；证据等级保持 `design-only`，`v0.6` 才可验收 `runnable-mvp` |

## User Acceptance

- [ ] 用户从 clean checkout 执行 `uv sync --frozen` 与 Success smoke，确认摘要字段、稳定性与可理解性。
- [ ] 用户执行 Expected failure，确认 exit 2、错误定位、空 success stdout 与无 `.bora/` 成功产物。
- [ ] 用户检查 implementation diff 与完整 gate 证据，确认范围仅为 Roadmap `v0.1` Config Core。
- [ ] 用户确认 README、Architecture、AGENTS 与 Roadmap 投影准确后，批准勾选 Version Index `v0.1`。

## Evaluation Record

### Round 1

- Critic: independent general-purpose subagent (`019fc2c1-3095-7683-a055-fbf0d0b3d0b4`)
- Review scope: full
- Evidence reviewed: Spec 00 Increment Contract；`src/bora/**`、examples、tests；README/ARCHITECTURE/AGENTS/ROADMAP；pytest 25→29 ids；public lock smokes；dependency direction
- Findings:
  1. (non-blocking) `PackageReader` Protocol 原位于 adapters — **已修**：迁入 `src/bora/config/ports.py`
  2. (non-blocking) 失败矩阵测试不全 — **已修**：补充 `invalid_format` / `unsupported_capability` / `missing_reference`
  3. (non-blocking) `/limits/memory_mb` allowlist 无 default leaf — **已修**：defaults 增加 `memory_mb`
  4. (non-blocking) acceptance 用 `-m bora.cli.main` 而非 `uv run bora` — 保留；与 console script 同一 Typer app；User Acceptance 用 README 命令
  5. (non-blocking) AGENTS 边界文案仍写「计划 composition」— 延后文档润色
- Selected fixes: (1)(2)(3) 如上
- Executor fixes: ports 拆分、测试补全、memory_mb default；重跑 ruff/pyright/pytest
- Deferred findings: AGENTS 措辞润色；entrypoint locator 更细校验 → 后续 Config/Harness Spec
- Validation rerun: `uv run pytest`、`ruff`、`pyright`、public lock smokes、strict specs validator
- Verdict: `pass-with-follow-ups`
