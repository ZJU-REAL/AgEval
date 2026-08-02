# BORA 文档（设计权威）

## 权威角色

本目录是 BORA **产品与技术设计的权威来源**（自包含）。实现、Roadmap、Active Spec 与代码均应对齐这里；冲突时**先改 `docs/`**，再同步下游。

| 问题 | 归属 |
| --- | --- |
| 产品是什么、成功标准、非目标 | [PRD.md](PRD.md) |
| 机制如何设计、边界如何切 | [`design/`](design/)（**全文**，勿外链 vault 代替） |
| 术语 | [glossary.md](glossary.md) |
| 当前/目标代码结构、依赖、生命周期地图 | [../ARCHITECTURE.md](../ARCHITECTURE.md)（**结构权威**；不重复设计长文） |
| Agent 交付路由、红线、校验 | [../AGENTS.md](../AGENTS.md) |
| Specs 局部政策 | [../specs/AGENTS.md](../specs/AGENTS.md) |
| 按 Core 的交付顺序与验收 | [../specs/ROADMAP.md](../specs/ROADMAP.md) |
| 实现期用户指定的绑定决策 | `specs/constitution/`（**仅在你明确要求时新增**） |

### 与 Spec-Driven Delivery 的分工

| SDD 工件 | 本仓位置 | 说明 |
| --- | --- | --- |
| 产品/设计规格 | **本目录** | 设计已定稿；日常不维护 vault |
| 结构地图 | `ARCHITECTURE.md` | current vs target、所有权、依赖 |
| 版本结果 | `specs/ROADMAP.md` | Core 表面 + `v0.x` 索引 |
| 实现增量 | `specs/active/` | 竖切 Spec |
| 可选绑定决策 | `specs/constitution/` | 默认空 |
| 通用模板/清单 | `$spec-driven-delivery` skill | 不复制进本仓 |

**不再**把 Obsidian vault 总文档当作日常权威。`docs/design/` 已完整迁入；vault 仅历史备份（见 `reference/`）。

## 设计文档目录（请按序阅读）

| 文档 | 内容 | vault 章节 |
| --- | --- | --- |
| [design/00-overview-and-product.md](design/00-overview-and-product.md) | 产品目标、红线、可见性投影、背景与设计修正 | 导语 + §0–§1 |
| [design/01-bora-core.md](design/01-bora-core.md) | BORA Core 五组机制与模块布局 | §2 |
| [design/02-task-package-and-config.md](design/02-task-package-and-config.md) | Task Package、`bora.yaml`、Config Core | §5–§6 |
| [design/03-harness-layer.md](design/03-harness-layer.md) | Harness 层职责与结构 | §3 |
| [design/04-harness-core-sdk.md](design/04-harness-core-sdk.md) | Harness Core（SDK）详细设计 | §7 |
| [design/05-runtime-core.md](design/05-runtime-core.md) | Runtime：Lifecycle / Provider / Agent Service / Env / Eval / Campaign | §8、§11 |
| [design/06-capability-adapter-visibility.md](design/06-capability-adapter-visibility.md) | Capability、Adapter 插件、可见性 | §9–§10 |
| [design/07-budget-evaluation-failure.md](design/07-budget-evaluation-failure.md) | Budget、Evaluation、失败语义 | §13–§15 |
| [design/08-conversion-security-testing.md](design/08-conversion-security-testing.md) | 转换、测试、安全边界 | §16–§18 |
| [design/09-owner-matrix-and-structure.md](design/09-owner-matrix-and-structure.md) | Owner 矩阵、决策检查表、目标结构、相关资料 | §19–§22 |
| [design/10-examples-database-52.md](design/10-examples-database-52.md) | database-52 对照与 MVP 主路径示意 | §4、§12 |

正文保留原 `## N.` / `### N.M.` 编号，便于与 vault 对照。

## 与 vault 总设计的对齐

历史长文：`ob-notes/inbox/BORA-v2/BORA 统一配置与动态 Harness 设计.md`（§0–§22）。

**本仓 `docs/design/` 承载同一套技术设计**，并作为后续 SDD / Spec 的**唯一设计维护面**。

### 有意保留的非语义差异

| 项 | 说明 |
| --- | --- |
| 产品全称 | 本仓统一为 **Bounded Orchestration for Runtime Agents**；vault 导语可能只写「BORA v2」 |
| 示意路径 | `database-52*` 标明为概念 package / 文档内示例；YAML 与代码片段仍完整在 docs |
| v0.9 源码路径 | 对照片段标明来自归档 v1，避免误读为当前 greenfield 树 |
| vault 双链 | §22 历史笔记改为标题列表；外链 URL 保留 |

除上表外，机制、红线、Core 边界、配置形状、Runtime/插件模型按 **docs ≡ vault 技术内容** 使用。

### 防漂移规则（后续 SDD）

1. 改设计只改 `docs/design/`（及必要时 PRD/glossary），再同步 Architecture / Roadmap / Active Spec。  
2. Active Spec **只链接** design 精确标题，不复制大段设计正文。  
3. 不以 vault 为日常编辑面。若对照发现不一致：**以 docs 为准**，或明确 PR 把 vault 某段合并进 docs 后再实现。  
4. 新增机制必须先有 design 段落，再写 Spec / 编码。  

## 同步规则

- 改设计 → 更新对应 `design/*`（及必要时 PRD/glossary）→ 再改 Architecture / Roadmap / Active Spec / 代码。  
- Active Spec **链接** design 精确章节，不复制长文。  
- Constitution **不**承载完整设计；只记录实现过程中你点名要固化的决策。  

## 可选：vault 备份软链接

若本机 `Developer/ob-notes` 与 `Developer/work` 并列，可存在：

```text
docs/reference/BORA-统一配置与动态-Harness-设计.md → vault 历史长文
```

**非权威、只读对照。** 禁止经软链接写入 vault。日常只维护本仓 `docs/design/`。
