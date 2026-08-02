# BORA

**Bounded Orchestration for Runtime Agents**

BORA 是 *Harness 的 Harness*：在统一的配置锁定、Attempt 生命周期、Provider 隔离、Capability API、可见性投影与独立评测下，运行 task-local 或 upstream Agent Harness，并绑定可复盘结果。

设计口令：**边界硬、契约薄、实现可胖**。

## 项目状态

| 项 | 值 |
| --- | --- |
| 代际 | v2 greenfield（不兼容归档 v1） |
| 设计 | 已写入 [`docs/design/`](docs/design/)（自包含） |
| 实现 | **未开始**（无 `src/` / CLI） |
| 证据 | `design-only` |
| 交付方法 | Spec-Driven Delivery（`$spec-driven-delivery`） |
| 活动 Spec | [specs/active/00-core-batch0-and-batch1-plan.md](specs/active/00-core-batch0-and-batch1-plan.md)（`v0.1` Config；实现需授权） |
| v1 参考 | `Developer/Archived/bora-v1`（只读） |

## 从哪里读起

### 给 Agent / 贡献者（交付 harness）

1. [AGENTS.md](AGENTS.md) — 权威链、当前事实、红线、校验  
2. [ARCHITECTURE.md](ARCHITECTURE.md) — 当前/目标结构、所有权、依赖、生命周期、数据流  
3. [specs/AGENTS.md](specs/AGENTS.md) — Specs 局部政策  
4. [specs/ROADMAP.md](specs/ROADMAP.md) — Core 交付顺序与验收  
5. 当前 Active Spec  

### 给设计读者

1. [docs/README.md](docs/README.md)  
2. [docs/design/00-overview-and-product.md](docs/design/00-overview-and-product.md)  
3. [docs/design/01-bora-core.md](docs/design/01-bora-core.md)  
4. 其余 `docs/design/02`–`10` 按需  

### 权威顺序（摘要）

```text
docs/design（机制） → ARCHITECTURE（结构） → ROADMAP（验收） → Active Spec → 代码/smoke
constitution/ 可选且默认空 —— 仅实现期用户点名决策
```

Obsidian vault **不是**日常权威。`docs/reference/` 仅历史备份说明。

## 交付如何组织

- **设计已定**，按 **BORA Core + Harness Core** 表面稳步实现（见 Roadmap）。  
- `v0.x` 是索引号；语义是 Config → Lifecycle → Provider → Capability → Harness Core → Evaluation + `bora run` → …  
- 每个 Active Spec：一个可验证增量、Decision Summary、前置条件闭包、success/expected-failure、工程门禁。  
- 通用写法与清单：skill `$spec-driven-delivery`。  

## 目标主路径（未实现）

```text
bora run <package> --task <id>
  → load_and_lock
  → Attempt + Provider views
  → harness(ctx) via Capability
  → stop writers → independent evaluator
  → flat Result + .bora/runs/<run-id>/
```

当前公开入口：**无**。

## 校验

```bash
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
git diff --check
```

## 目录

```text
docs/     设计权威
specs/    Roadmap / Active Specs / BLOCKED / 可选 constitution
AGENTS.md / ARCHITECTURE.md  交付与结构 harness
```

实现代码目录将在 Spec 授权后出现（见 Architecture Target 树）。

## 许可

私有研发工作区；公开发布策略未定。
