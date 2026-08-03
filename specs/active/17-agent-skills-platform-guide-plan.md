# Spec 17 — Agent Skills 平台使用指南

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-03 |
| Scope | `v0.18`；仓库 `skills/` 布局；平台总览 / CLI / config / SDK-package 使用指南（面向 coding agent） |
| Type | docs |
| Priority | P1 |
| Status | in-progress |
| Planning gate | review（待用户验收；implementation not started） |
| Completed | pending |
| Independent review | off |
| Dependencies | 当前公开 CLI 与 `docs/` 基线；建议在机制主轴（Spec 12–16）推进时同步回写，但本 Spec **不**要求 v0.17 先勾选才能起草 **已落地** 表面的 skills |
| Decisions | [Roadmap v0.18](../ROADMAP.md#v018--agent-skills平台使用指南)、[PRD](../../docs/PRD.md)、[design/02](../../docs/design/02-task-package-and-config.md)、[design/03](../../docs/design/03-harness-layer.md)、[design/04](../../docs/design/04-harness-core-sdk.md)、[design/00 红线](../../docs/design/00-overview-and-product.md#02-红线) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `no` |
| User decision required | `yes` |
| Ready for acceptance now | `yes` |
| Current blockers | `1` |
| Potential blockers | `1` |

- Next action: 等待用户验收本 Spec 与 Roadmap v0.18；验收前不创建 skills 目录或改 production 代码。

### Current blockers

- `B1` (Owner: User): 规划文档尚未验收为实施基线。

### Potential blockers

- `R1` (Owner: Agent / Phase 0): 宿主 agent 运行时如何发现仓库内 skills（相对路径、symlink、用户 skill 安装）需在 Phase 0 冻结一种可重复方式，避免每人一套加载法。

## Phases

- [ ] Phase 0: 盘点已落地公开表面 + skill 格式与加载约定
- [ ] Phase 1: `skills/` 布局 + 平台总览 skill
- [ ] Phase 2: CLI skill
- [ ] Phase 3: Config / package skill
- [ ] Phase 4: SDK / harness skill + 红线速查
- [ ] Phase 5: walkthrough 验收、链接一致性与状态文档同步

## Background

### Problem

仓库已有 `docs/` 设计权威和 `examples/`，但 coding agent 进仓后仍常：

- 不知道先读哪、Core 和 harness 谁说了算；
- CLI 参数与失败码靠猜；
- 写 `bora.yaml` / harness 时抄错所有权（自提 PASS、按 bench 名分支、密钥进配置）。

需要一份**给 agent 用的短路径说明**（Skills），把「怎么用平台」说清楚，并链回 design，而不是再造第二套长文。

### Current Behavior

- `docs/design/`、`docs/PRD.md`、`README.md`、`AGENTS.md` 已存在；面向人类，agent 检索成本高。
- 无仓库级 `skills/`（或等价）约定；无「只靠 skill 完成一次 package 理解」的验收。
- 机制主轴 v0.13–v0.17 仍在规划/未实施：Skills **不得**把未落地能力写成已可用。

### Goals and Non-goals

- Goal: 固定 `skills/` 目录与每个 skill 的 `SKILL.md`（+ 可选 `references/`）形状。
- Goal: 至少四块内容：**总览**、**CLI**、**config/package**、**SDK/harness**；均用说人话写步骤与禁区，并链 design 精确节。
- Goal: 写清「证据等级 / 不可声称」与常见反模式，避免 agent 越权改 Core 或伪造 PASS。
- Non-goal: 不替代 `docs/design/` 机制权威；不写完整 API 参考手册；不实现 Runtime 新功能。
- Non-goal: 不做网站文档站、不做插件市场 skill、不把 vault 当权威。
- Evidence boundary: 验收的是「agent 可按 skill 操作与理解」；不因有 skills 升级 `runnable-mvp` / `isolated` / `real-benchmark-verified`。

## Increment Contract

### Starting Runnable Baseline

- Public entrypoint: `uv run bora --help`、`bora lock` / `bora run` 与 README 安装步骤。
- Production composition root: `src/bora/application/composition.py`（skills 只描述，不改 authority）。
- Baseline smoke: 现有 example packages 可 lock；design 可读。
- Observable result: 无 skills 目录。

### User Story

作为在本仓干活的 coding agent，我打开 skills 后知道：BORA 干什么、先跑哪条 CLI、package 该长什么样、harness 里能写什么不能写什么——并链到 design 核对，而不是自己发明一套配置语义。

### Scope Boundary

- Included: `skills/` 布局、总览/CLI/config/SDK 四 skill（可拆可合）、加载说明、反模式表、与 docs/examples 的链接、walkthrough 清单。
- Deferred: 未实现命令的完整手册；Campaign 全文、插件分发、durable、VM 等 `v0.19+` 主题 skill（可占位「未交付」一行）。
- Out of scope: 修改 Core 行为；把 design 全文搬进 skill。

### Prerequisite Audit Details

<details>
<summary>展开前置来源、供应、验证与清理</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| 已落地 CLI 与 example | `baseline-verified` | README / 现有 acceptance | `uv sync --frozen`；`bora --help`；`bora lock examples/core/config-minimal` | exit 0 与稳定摘要字段 | 不删用户数据；测试用 run 目录按 Attempt 清理 |
| design 权威文本 | `baseline-verified` | `docs/design/*`、PRD | 只读链接，不复制长文 | skill 内链接可解析 | 无运行时资源；仅保留文档 |
| Skill 加载约定 | `phase-produced` | Agent / Phase 0 | 在 README/AGENTS 写清：本仓 skills 路径 + 推荐安装/引用方式 | 另一会话能按文档找到 SKILL.md | 不改用户全局 skill 除非文档要求可选 symlink |
| Skills 正文与 references | `phase-produced` | Agent / Phase 1–4 | 按章节撰写，字段与 `bora --help`、example 对齐 | 抽检命令/字段一致；反模式有禁令 | 无运行时资源 |
| Walkthrough 清单 | `phase-produced` | Agent / Phase 5 | `skills/` 内或 `specs/` 旁检查表：lock example → 指出改 config/harness 路径 | 人工或脚本勾选全过 | 无运行时资源；仅保留文档 |

</details>

### Runnable Acceptance

- Success: 按 walkthrough，仅依赖 skills + 公开入口完成「理解并指出如何改一个 example package」；记录引用的 skill 路径。
- Expected failure（文档向）: skill 明确禁止的反模式（completed=PASS、密钥进 yaml、按 bench 名写 Adapter）不得被 skill 表述为推荐做法。
- Regression: 不改坏现有 pytest / public smokes；strict Specs validator 通过。
- Observable evidence: `skills/**/SKILL.md` 存在；README/AGENTS 有入口；一致性抽检记录（可放 Phase 5 勾选）。

### Extension Seams

- 后续机制落地后：只增补 references 小节或「新能力」短节，不另起互相矛盾的 skill 品牌。
- 可选：用户级 install 说明（symlink 到 `~/.agents/skills` 等）写在总览，默认以仓内路径为准。

## Design

> Inherited: PRD 作者面；design/00 红线；design/02 package+config；design/03 harness；design/04 SDK。  
> Local delta: 冻结 **agent 消费面** 的目录与写作规范，不新增 Runtime API。

### 推荐目录（Phase 1 可微调命名，语义固定）

```text
skills/
├── README.md                 # 人类/agent：有哪些 skill、何时用
├── bora-platform/
│   └── SKILL.md              # 总览与读文档顺序
├── bora-cli/
│   └── SKILL.md              # lock / run / campaign …
├── bora-config/
│   ├── SKILL.md              # bora.yaml + package layout
│   └── references/           # 可选：字段表、失败码
└── bora-sdk-harness/
    ├── SKILL.md              # HarnessContext / Session / Tool
    └── references/           # 可选：最小 harness 骨架
```

### 写作规范

1. **权威顺序**：skill 操作说明 → 链 `docs/design` / PRD；冲突以 docs 为准。  
2. **只写已落地**：未实现标「未交付」或省略；禁止「假装可用」。  
3. **说人话**：步骤用「做什么 → 跑什么 → 看到什么」；术语首次可括号 gloss。  
4. **禁区表**：PASS 来源、密钥、Adapter 命名、可见性/gold、硬顶 vs 事后 usage。  
5. **无 secret**：示例只用占位符 env 名。

## Phase 0: 盘点与加载约定

### Goal

列出当前真实 CLI/package/SDK 表面，并冻结 skill 如何被 agent 找到。

### Tasks

- 从 `bora --help`、README、examples 列出可写进 skill 的命令与路径。
- 对比 design 与实现，标记「已落地 / 规划中」。
- 写加载约定草案（仓内路径优先）。

### Files

- `skills/README.md`（草案可先在 Spec 附件或 Phase 1 落盘）
- `README.md` / `AGENTS.md`（仅加载说明占位，实施期改）

### Acceptance Criteria

- [ ] 已落地表面清单与「禁止声称」清单成文，无未核实命令。
- [ ] `R1` 关闭：加载方式可重复说明。
- [ ] 用户未验收前可不落盘 skills（本 Phase 产出可暂存 Spec 勾选与清单文件路径）。

## Phase 1: 布局 + 平台总览

### Goal

创建 `skills/` 骨架与 `bora-platform` 总览。

### Tasks

- 创建目录与 `skills/README.md`。
- 写总览：产品一句话、Core/Harness/package、证据等级、读序（AGENTS → design → examples）。
- 链 PRD 与 design/00–01。

### Files

- `skills/README.md`
- `skills/bora-platform/SKILL.md`

### Acceptance Criteria

- [ ] 总览 5 分钟内可读完主干；无与 AGENTS 红线冲突。
- [ ] 相对链接有效。

## Phase 2: CLI skill

### Goal

agent 能按 skill 正确调用已暴露 CLI 并解读常见失败。

### Tasks

- 写 `bora-cli`：安装、`lock`/`run`/`campaign`（及已有 status 类）、成功/失败判据、evidence 目录怎么找。
- 与 `--help` 对齐；未实现子命令不写。

### Files

- `skills/bora-cli/SKILL.md`
- 可选 `skills/bora-cli/references/exit-codes.md`

### Acceptance Criteria

- [ ] 每条推荐命令可在 clean checkout 复现或标明前置（如需登录 Codex）。
- [ ] 失败例有稳定错误语义说明（如 unknown_profile）。

## Phase 3: Config / package skill

### Goal

agent 能新建或修改 package 时不踩所有权坑。

### Tasks

- 写 layout allowlist、`bora.yaml` 分段、parameters vs envelope、profile 引用。
- 反模式：第二配置源、密钥进文件、按 task/bench 名分支。

### Files

- `skills/bora-config/SKILL.md`
- 可选 `references/bora-yaml-map.md`

### Acceptance Criteria

- [ ] 与 design/02 一致；example 路径正确。
- [ ] 至少 5 条「禁止」可核对。

## Phase 4: SDK / harness skill

### Goal

agent 写 harness 时只用 Capability/SDK 合同。

### Tasks

- 写 HarnessContext、Session、Tool/Guard、不得绑定具体 executor 实现、PASS 只来自 evaluator。
- 最小 skeleton 指向 example，不贴过时大段代码。

### Files

- `skills/bora-sdk-harness/SKILL.md`
- 可选 `references/minimal-harness.md`

### Acceptance Criteria

- [ ] 与 design/03–04 一致。
- [ ] 明确 HarnessTerminal.completed ≠ PASS。

## Phase 5: Walkthrough 与同步

### Goal

可验收的「跟 skill 走一遍」与仓内入口同步。

### Tasks

- 写 walkthrough 清单并执行一次。
- 更新 README、AGENTS 当前事实；Roadmap 勾选仅在证据齐后。
- 抽检 skill ↔ help ↔ example 一致性。

### Files

- `skills/README.md`（walkthrough 链接）
- `README.md`、`AGENTS.md`
- `specs/ROADMAP.md`
- `specs/active/17-agent-skills-platform-guide-plan.md`

### Acceptance Criteria

- [ ] Walkthrough 全勾；记录路径。
- [ ] strict validator、相对链接、`git diff --check` 通过。
- [ ] 无 secret；未落地能力未写成已可用。
- [ ] Version Index `v0.18` 仅在本 Spec 完成与规定审查后勾选。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Skills 变成第二设计权威 | 强制链 docs；冲突以 design 为准写进总览 |
| 写了未实现命令 | Phase 0 清单 + Phase 5 与 `--help` 对表 |
| 长文复制 design | 限篇幅；细节用链接 |
| 加载方式因人而异 | Phase 0 冻结仓内路径说明 |

## User Acceptance

- [ ] 用户接受 `skills/` 布局、四块内容范围、与 design 权威关系，以及「只描述已落地表面」规则，并单独授权实施本 Spec。
