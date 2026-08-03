# BORA

**Bounded Orchestration for Runtime Agents**

BORA 是 *Harness 的 Harness*：在统一的配置锁定、Attempt 生命周期、Provider 隔离、Capability API、可见性投影与独立评测下，运行 task-local 或 upstream Agent Harness，并绑定可复盘结果。

设计口令：**边界硬、契约薄、实现可胖**。

## 项目状态

| 项 | 值 |
| --- | --- |
| 代际 | v2 greenfield（不兼容归档 v1） |
| 设计 | 已写入 [`docs/design/`](docs/design/)（自包含） |
| 实现 | **v0.7 HC-2/3 surfaces 可跑**（parent-bound Session + Tool）；terminal L1 / env / campaign 为**部分切片**；v0.8–v0.12 全文未闭合（见 Active Spec Implementation Progress） |
| 公开 entrypoint | `bora lock` / `bora run` / `bora campaign`（经 `application/composition.py` 装配） |
| 证据 | L0/L1 named packages + plugin HTTP 第二后端 + Env Manager + campaign preadmit + `bora submit/status/cancel`；Version Index **`v0.1`–`v0.12` 已勾**（Critic 授权收口）；**不得**扩写全 suite `isolated` / `real-benchmark-verified` |
| 交付方法 | Spec-Driven Delivery（`$spec-driven-delivery`） |
| 活动 Spec | [specs/active/00-core-batch0-and-batch1-plan.md](specs/active/00-core-batch0-and-batch1-plan.md) 起；依赖链见 Roadmap |
| v1 参考 | `Developer/Archived/bora-v1`（只读） |

## 安装（v0.1）

需要 [uv](https://docs.astral.sh/uv/) 与 CPython 3.12：

```bash
uv sync --frozen
uv run bora --help
```

## 公开 CLI（当前事实）

| 命令 | 含义 | 证据边界 |
| --- | --- | --- |
| `bora lock` | Config Core 锁定摘要 | 工程检查点；非 `runnable-mvp` |
| `bora run` | 单 Trial 前台 Attempt 竖切（L0） | 离线 fail-closed 已回归；**真实 Agent PASS 需登录 Codex 并记录证据** |
| `bora campaign` | 前台串行 matrix（`/parameters/*`） | seed 等 allowlisted variant **已注入** lock digest；非完整 campaign policy |

## 公开检查点：`bora lock`

从 clean checkout 锁定一份 Task Package，得到**确定性、无 secret** 的 JSON 摘要（stdout）。
这是 Config Core 工程检查点，**不**创建 Run/Attempt、**不**启动 Agent/Evaluator。

### Success

```bash
uv run bora lock examples/config-minimal --task config-minimal
```

- Exit `0`
- Stdout：单一 JSON，含 `format`、`task_id`、`resolved_references`、`resolution`、`digest`
- 不默认写入 `.bora/` 成功 lock

可选覆盖（allowlisted JSON Pointer）：

```bash
uv run bora lock examples/config-minimal --task config-minimal --set /parameters/seed=7
```

### Expected failure

```bash
uv run bora lock examples/config-invalid --task config-invalid
```

- Exit `2`
- Stderr：稳定 `unknown_profile`（及 package-relative location）
- Stdout 为空；不创建成功 lock 产物

## Lifecycle 检查点（v0.2）

公开产品入口仍是 `bora lock`。Lifecycle Core 通过 application acceptance 验证：

```bash
uv run pytest tests/acceptance/test_lifecycle_application.py -k success_trace -q
```

test double 仅在 `tests/doubles/`，不进入 production composition，不声明 `runnable-mvp`。

## 从哪里读起

### 给 Agent / 贡献者

1. [AGENTS.md](AGENTS.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [specs/AGENTS.md](specs/AGENTS.md)
4. [specs/ROADMAP.md](specs/ROADMAP.md)
5. 当前 Active Spec

### 给设计读者

1. [docs/README.md](docs/README.md)
2. [docs/design/00-overview-and-product.md](docs/design/00-overview-and-product.md)
3. [docs/design/01-bora-core.md](docs/design/01-bora-core.md)
4. 其余 `docs/design/02`–`10` 按需

## 工程门禁

```bash
uv sync --frozen
uv run ruff format --check src tests
uv run ruff check src tests
uv run pyright
uv run pytest
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
git diff --check
```

## 目标主路径（尚未作为产品路径交付）

```text
bora run <package> --task <id>    # Roadmap v0.6
  → load_and_lock
  → Attempt + Provider views
  → harness(ctx) via Capability
  → stop writers → independent evaluator
  → flat Result + .bora/runs/<run-id>/
```

当前公开入口：仅 **`bora lock`**（Config checkpoint）。

## 目录（实现相关）

```text
src/bora/     production package（cli / application / config / adapters）
examples/     仓库拥有的 Task Package fixtures
tests/        unit + acceptance
docs/         设计权威
specs/        Roadmap / Active Specs / BLOCKED
```
