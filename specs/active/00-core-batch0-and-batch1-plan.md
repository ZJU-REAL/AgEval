# Spec 00 — 批次 0–1：工程骨架与 Config Core

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-02 |
| Scope | engineering skeleton; v0.1 BORA Core 1 Config; package layout; lock/inspect |
| Type | feat |
| Priority | P0 |
| Status | in-progress |
| Completed | pending |
| Independent review | off |
| Dependencies | none |
| Design | [docs/design/01](../../docs/design/01-bora-core.md)、[docs/design/02](../../docs/design/02-task-package-and-config.md)、[ROADMAP v0.1 Config Core](../ROADMAP.md#v01--bora-core-1config) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | no |
| User decision required | yes |
| Ready for acceptance now | no |
| Current blockers | 1 |
| Potential blockers | 1 |

- Next action: 用户授权实现后启动 Phase 0（pyproject + CLI 骨架）。

### Current blockers

- `B1`（Owner: user）: 尚未授权开始实现；当前仅完成 docs/specs 重构。

### Potential blockers

- `R1`（Owner: Phase 0）: 工程 Python 需 ≥3.12（可用 uv 供应）。

## Phases

- [ ] Phase 0: 工程骨架、工具链、`bora --help`
- [ ] Phase 1: Package 布局 + `load_and_lock` + example 静态 package
- [ ] Phase 2: inspect/lock CLI 与失败路径
- [ ] Phase 3: 门禁、Roadmap `v0.1` 证据、docs/Architecture 当前树同步

## Background

### Problem

设计已在 `docs/design` 自包含，但仓库无可安装代码与 Config Core。

### Goals and Non-goals

- Goals: 批次 0 骨架 + `v0.1` BORA Core 1 Config 可验证。  
- Non-goals: 本 Spec **不**要求真实 Codex、`bora run` 全竖切（属 Roadmap `v0.6` / 后续 Spec）、Docker、Campaign。  

### Key Insight

按 Core Roadmap 稳步交付；首条用户竖切在 Config 与后续 Lifecycle/Capability 就绪后的 Roadmap `v0.6` Spec。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: none  
- Baseline smoke: none  
- Observable result: design-only docs  

### User Story

As a developer, I can install BORA and run a lock/inspect command on an example package so that I get a deterministic locked config summary or a clear validation error.

### Scope Boundary

- Included: Roadmap `v0.1`、批次 0 骨架、一个 example package 的 yaml  
- Deferred: `v0.2+` 后续 BORA Core、`v0.5` / `v0.7` Harness Core、`v0.6` 真实 Agent 竖切  

### Prerequisite Audit Details

<details>
<summary>Expand prerequisite sources, setup, verification, and cleanup</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| uv | `external-accepted` | operator | 安装 uv | `uv --version` 成功 | 无仓库资源 |
| Python ≥3.12 | `phase-produced` | Phase 0 | `uv python install 3.12` 并 pin | `uv run python --version` ≥3.12 | uv 管理解释器 |
| Example package | `phase-produced` | Phase 1 | 写入 `examples/…` | load_and_lock 成功 | git 管理文件 |

</details>

### Runnable Acceptance

- Success smoke: 冻结后的 lock/inspect 命令对 example 成功并打印锁定摘要  
- Expected failure: 故意破坏的 package / 未知 task → 非 0  
- Regression smokes: none  
- Observable evidence: CLI 输出 +（可选）写出的 lock 摘要文件  

### Extension Seams

- Config 模型字段可扩展；本 Spec 只锁定 docs 中的最小子集并在测试中固定  

## Design

> Inherited design: [docs/design/02-task-package-and-config.md](../../docs/design/02-task-package-and-config.md)、[docs/design/01-bora-core.md](../../docs/design/01-bora-core.md)、[ARCHITECTURE.md](../../ARCHITECTURE.md)  
>
> Local delta: 仅落地 **Config Core 最小可测字段集** + 工程骨架；不实现 Provider / Capability / Evaluator / Codex。

### Control Flow

```text
operator
  → bora --help | bora <lock|inspect> <package> [--task id]
  → cli
  → application use case
  → config.load_and_lock
  → stdout summary and/or optional .bora/ lock artifact
  → exit code
```

### Data Flow

| 数据 | 方向 | 规则 |
| --- | --- | --- |
| package 路径 / task id / overrides | CLI → Config | 无 secret |
| `bora.yaml` | fs → Config | 唯一规范读取 |
| `LockedTaskConfig` / 摘要 | Config → CLI | 可复盘；无 credential |
| 校验错误 | Config → CLI | fail-closed；无伪成功 |

### Reference Data Structures

- 最小 `bora.yaml` 字段集：Phase 1 用测试固定清单，必须是 design/02 的真子集。  
- 错误分类：invalid package / unknown task / validation failed（名称以实现为准）。  

### Core Functions and Interfaces

- `load_and_lock(package, task, variant, overrides) -> LockedTaskConfig`  
- CLI 子命令名在 Phase 2 冻结并写入 README  
- composition root：仅 wiring config + fs adapter  

### Engineering Gates（Spec 完成时）

- [ ] 可复现安装（`uv sync` 或等价）  
- [ ] Ruff、Pyright、pytest 通过  
- [ ] `validate_specs_workspace.py . --strict`  
- [ ] README 写明精确 success / expected-failure 命令  

## Phase 0: 工程骨架

### Goal

可安装的 Python 包与 CLI 帮助入口。

### Tasks

- 添加 `pyproject.toml`、`src/bora/`、tooling  
- CLI 入口与最小导入测试  

### Files

- `pyproject.toml`、`src/bora/**`、`tests/**`、README 安装节  

### Acceptance Criteria

- [ ] 可安装；`bora --help` 成功  
- [ ] Ruff/Pyright/pytest 基线通过  
- [ ] 临时集成缺口（若有）记在本 Spec  

## Phase 1: load_and_lock

### Goal

example package 可锁定；非法输入 fail-closed。

### Tasks

- schema + loader + 测试  
- `examples/<pkg>/` 最小 `bora.yaml`  
- 文档化本 Spec 字段白名单（链 design/02）  

### Files

- `src/bora/config/**`、`examples/**`、`tests/**`  

### Acceptance Criteria

- [ ] 合法 package lock 成功  
- [ ] 缺字段 / 未知 task 失败  
- [ ] 单元测试覆盖上述路径  

## Phase 2: CLI 路径

### Goal

用户可调用的 lock/inspect 与稳定 exit code。

### Tasks

- application use case + CLI 子命令  
- 冻结 success / expected-failure 命令字符串  

### Acceptance Criteria

- [ ] Success 输出可解析摘要  
- [ ] Expected failure 非 0 且无伪成功  
- [ ] 命令写入 README 与本 Spec Runnable Acceptance  

## Phase 3: 同步与 Roadmap 证据

### Goal

结构与版本投影与实现一致。

### Tasks

- 更新 Architecture **Current** 树  
- 更新 root/specs AGENTS「当前事实」  
- 全量工程门禁  

### Acceptance Criteria

- [ ] Architecture Current 反映真实 `src/`  
- [ ] Roadmap `v0.1` 所需证据齐备（勾选在用户验收后）  
- [ ] specs validator strict 通过  

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 范围膨胀进 Runtime/Codex | Non-goals 明确；拒绝越界文件 |
| schema 与 design 漂移 | 测试固定字段表 + 链接 design/02 |
| 把 lock 当成 runnable-mvp | 证据等级仍非 Agent 路径；README 写明 |

## User Acceptance

- [ ] 用户执行冻结的 success 与 expected-failure 命令，确认输出可理解  
- [ ] 用户确认可以勾选 Roadmap `v0.1`  
