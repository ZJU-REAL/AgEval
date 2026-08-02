# BORA Specs 指令

本文件是 **Specs 工作区局部路由与政策**：足够短以便每次加载，但包含无 skill 时也能工作的权威链、不变量、命名、同步与校验。  

通用模板、完成清单、螺旋写法见 **`$spec-driven-delivery`**（`references/document-contracts.md`、`spiral-delivery.md`、`review-checklists.md`）。  
**设计长文不在这里**，在 [`../docs/design/`](../docs/design/)。

## 目录地图

```text
../docs/              设计权威（PRD + design 00–10 自包含）
../ARCHITECTURE.md    结构权威（当前/目标、所有权、依赖、生命周期）
../README.md          人类入口
ROADMAP.md            Core 表面交付与版本验收（v0.x 为索引）
BLOCKED.md            执行期意外决策（newest-first；含插入标记）
constitution/         可为空；仅用户指定的实现期绑定决策
research/             未决问题（不可伪装成已接受决策）
active/               实现增量 Spec（NN-*-plan.md）
archive/              已完成/取消的历史 Spec
```

## 权威顺序

```text
docs/（设计）
  → ../ARCHITECTURE.md（结构）
  → ROADMAP.md（版本验收）
  → Active Spec（增量）
  → 公开 smoke / 代码 / 测试 / evidence

constitution/（可选）—— 不覆盖 docs
BLOCKED.md —— 低于权威链；改语义时必须回写权威文件
```

冲突：停实现 → 改最高权威 → 同步下游。详见 [../AGENTS.md](../AGENTS.md)。

## 必读顺序

1. [../ARCHITECTURE.md](../ARCHITECTURE.md)  
2. 相关 [../docs/design/](../docs/design/) 章节（精确链接，勿整篇粘贴进 Spec）  
3. [ROADMAP.md](ROADMAP.md) 对应 `v0.x`  
4. 完整所属 Active Spec（先读 **Decision Summary**）  
5. 若存在：相关 `constitution/*`  
6. 实施/修复时：[BLOCKED.md](BLOCKED.md)  

## 项目不变量与禁止项

### 交付形态

- 产品：**Bounded Orchestration for Runtime Agents（BORA）**；v2 greenfield。  
- 设计已定：按 **BORA Core / Harness Core** 表面推进（见 Roadmap），不是探索式改方向。  
- **禁止**把完整设计写入 constitution；constitution 仅在用户明确要求时新增 `YYYY-MM-DD-<topic>.md`。  
- 改设计 → 先 `docs/design/`；改结构 → 先 Architecture；改验收 → 先 Roadmap。  
- Active Spec **链接** design 精确标题；本地只写 **Local delta**。  
- `active/` **无数量上限**。依赖约束实施/完成顺序，不阻止提前撰写已确认 Spec。  
- 第一个**用户可运行产品竖切**在 Roadmap `v0.6`；`v0.1` 可为 lock/inspect 等中间可验证结果。  
- 文档规划 ≠ 实现授权：未授权不创建 production 源码、不勾选 Roadmap 完成。  

### 运行时与安全（Specs 写作时不得写反）

- Core 五组 + 可见性投影；workflow 归 package Harness。  
- `completed` ≠ PASS；独立 evaluator。  
- secret 不进 lock/evidence/Harness 默认环境。  
- 硬顶执行前强制；事后 usage ≠ hard budget。  
- Adapter 禁止 Benchmark/task 名分支。  
- Control Plane 不 import task-local harness/evaluator 模块。  
- 第三方 Agent SDK 不得成为 Core authority。  

### 证据与验收

- Fixture/mock ≠ 公开 smoke（当版本要求真实 Agent 时）。  
- 证据等级：`design-only` | `runnable-mvp` | `isolated` | `real-benchmark-verified`；不得从单测升级。  
- 每个 implementation Spec 收口：production public entrypoint（或该版本约定的可调用入口）、success、expected failure、受影响 regression、工程门禁、文档同步。  
- 独立评审默认 **off**；仅 `Independent review: required` 时写 Evaluation Record 并作为完成 gate。  
- Decision Summary 五项布尔/计数必须与列表一致；Current blockers 只含挡住下一步的项；Phase TODO 不算 blocker。  
- 前置条件表六列、三类：`baseline-verified` | `phase-produced` | `external-accepted`；env 只作 locator。  
- 执行期安全可逆选择：先 `BLOCKED.md` `resolved-autonomously`；否则 `awaiting-user`。  

## 命名与生命周期

| 类型 | 命名 | 状态 |
| --- | --- | --- |
| Constitution | `YYYY-MM-DD-<topic>.md` | accepted 历史在文件内 History |
| Research | `YYYY-MM-DD-<topic>-research.md` | `open` → `concluded` → `superseded`/archive |
| Active Spec | `NN-<topic>-plan.md` | `in-progress` → `completed`/archive；或 `review`；或 `cancelled`/archive |
| Roadmap 版本 | Index 中 `- [ ] \`v0.x\` — …` | 仅 Index 勾选表示版本完成 |

完成 Spec 前：新 success、expected failure、受影响 regression、工程 gates、docs 同步、明确要求的 User Acceptance。  
`completed` 后写入完成日与延期项，再移入 `archive/`，并更新所有入链。

## 同步矩阵（本仓）

| 变更 | 更新 |
| --- | --- |
| Phase / blocker / next action | Active Spec Decision Summary |
| 未预期执行选择 | `BLOCKED.md` 顶部 + 必要时权威文件 |
| 设计语义 | `docs/design/*` → Architecture 相关节、Roadmap、Spec 链接 |
| 目录/依赖/composition | [../ARCHITECTURE.md](../ARCHITECTURE.md) + root/specs AGENTS |
| 版本验收 | `ROADMAP.md` + Spec + README 状态 |
| 用户入口命令 | `README.md` + Roadmap/Spec 冻结命令 |
| Spec 归档 | 全库相对链接改为 `archive/` 路径 |

创建/评审 Active Spec 时：默认只改所属 Spec 与必要 Research；README、Architecture、docs、Roadmap 投影列入**该 Spec 最后 Phase**（用户要求立即改权威文件除外）。

## 校验

```bash
# 在仓库根
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
git diff --check
```

实现开始后另加 Active Spec 中的 install / Ruff / Pyright / pytest / 公开 smoke。

## Skill 指针

| 需要 | 读 skill 内 |
| --- | --- |
| Roadmap / Active Spec 结构 | `references/document-contracts.md` |
| 工作区与权威 | `references/workspace-contract.md` |
| Architecture 必选节 | `references/architecture-contract.md` |
| docs 目录职责 | `references/docs-contract.md`（注意：本仓 docs 为设计权威，见 root AGENTS 特例） |
| 完成/审查清单 | `references/review-checklists.md` |
| 竖切与成熟度措辞 | `references/spiral-delivery.md` |
