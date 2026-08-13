# BORA 文档（设计权威）

## 权威角色

本目录是 BORA **产品与技术设计的权威来源**（自包含）。实现、Issues、代码与读者向文档均应对齐这里；冲突时**先改 `docs/`**，再同步下游。

| 问题                                  | 归属                                                                     |
| ------------------------------------- | ------------------------------------------------------------------------ |
| 产品是什么、成功标准、非目标          | [PRD.md](PRD.md)                                                         |
| 机制如何设计、边界如何切              | [`design/`](design/)（**全文**，勿外链 vault 代替）                      |
| 术语                                  | [glossary.md](glossary.md)                                               |
| 当前/目标代码结构、依赖、生命周期地图 | [../ARCHITECTURE.md](../ARCHITECTURE.md)（**结构权威**；不重复设计长文） |
| Agent 交付路由、红线、校验            | [../AGENTS.md](../AGENTS.md)                                             |
| 增量交付与验收跟踪                    | [GitHub Issues](https://github.com/ZJU-REAL/BORA/issues)                 |
| 读者向「怎么用」                      | [../website/](../website/)（**非**设计权威；与本文冲突以本文为准）       |

### 与 website / 交付跟踪的分工

| 工件               | 本仓位置                      | 说明                               |
| ------------------ | ----------------------------- | ---------------------------------- |
| 产品/设计规格      | **本目录**                    | 机制与红线权威；自包含             |
| 结构地图           | `ARCHITECTURE.md`             | current vs target、所有权、依赖    |
| 增量与验收         | GitHub Issues                 | 日常推进主轨道                     |
| 读者向产品文档     | `website/`                    | 从本目录**提炼重写**；禁止整页镜像 |
| SPA / 服务开发细节 | `apps/*`、`services/*` README | 非产品教程主入口                   |

**不再**维护 `specs/`（Active Spec / ROADMAP / constitution）。增量交付与验收跟踪 → **GitHub Issues**。历史见 Git。  
**不再**把 Obsidian vault 总文档当作日常权威。`docs/design/` 已完整迁入；vault 仅历史备份（见 `reference/`）。  
**不**新增 `docs/status/` 或 design 内进度表；`design/` 只写稳定机制。

## 设计文档目录（请按序阅读）

完整读序与 Runtime 子文索引见 [design/README.md](design/README.md)。

| 文档                                                                                     | 内容                                                                                   |
| ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [design/00-overview-and-product.md](design/00-overview-and-product.md)                   | 产品目标、红线、可见性投影、背景与设计修正                                             |
| [design/01-bora-core.md](design/01-bora-core.md)                                         | BORA Core 五组机制与模块布局                                                           |
| [design/02-task-package-and-config.md](design/02-task-package-and-config.md)             | Database / Task、`bora.yaml` / `task.yaml`、Config Core                                |
| [design/03-harness-layer.md](design/03-harness-layer.md)                                 | Harness 层职责与结构                                                                   |
| [design/04-harness-core-sdk.md](design/04-harness-core-sdk.md)                           | Harness Core（SDK）详细设计                                                            |
| [design/05-runtime/](design/05-runtime/)                                                 | Runtime：Lifecycle / Provider / Agent Service（ACP）/ Env / Eval / Evidence / Campaign |
| [design/05-runtime-core.md](design/05-runtime-core.md)                                   | stub → `05-runtime/`（兼容旧链）                                                       |
| [design/06-capability-adapter-visibility.md](design/06-capability-adapter-visibility.md) | Capability、Adapter 插件、可见性                                                       |
| [design/07-budget-evaluation-failure.md](design/07-budget-evaluation-failure.md)         | Budget、Evaluation、失败语义                                                           |
| [design/08-conversion-security-testing.md](design/08-conversion-security-testing.md)     | 转换、测试、安全边界                                                                   |
| [design/09-owner-matrix-and-structure.md](design/09-owner-matrix-and-structure.md)       | Owner 矩阵、决策检查表、目标结构、相关资料                                             |
| [design/10-examples-database-52.md](design/10-examples-database-52.md)                   | 设计意图下的示例对照（非进度）                                                         |
| [design/11-extension-plugins.md](design/11-extension-plugins.md)                         | 扩展点 L0–L5、注册表、lock bindings、`bora.plugin/1`、Recognition ≠ L0 host-ready ≠ L1 bake-declared、`--probe` |
| [design/12-hub-dataset-and-leaderboard.md](design/12-hub-dataset-and-leaderboard.md)     | Dataset draft/release、dataset ACL、Leaderboard 完备性、个人主页                       |

正文标题**不再**沿用 vault 总文档的 `## N.` / `### N.M.` 序号（避免跨文件序号断裂）；文件名前缀 `00`–`12` 仍作读序。Runtime 已按执行链拆分为 `05-runtime/*`。

## 与 vault 总设计的对齐

历史长文：`ob-notes/inbox/BORA-v2/BORA 统一配置与动态 Harness 设计.md`（§0–§22）。

**本仓 `docs/design/` 承载同一套技术设计**，并作为机制规格的**唯一设计维护面**。

### 有意保留的非语义差异

| 项            | 说明                                                                                   |
| ------------- | -------------------------------------------------------------------------------------- |
| 产品全称      | 本仓统一为 **Bounded Orchestration for Runtime Agents**；vault 导语可能只写「BORA v2」 |
| 示意路径      | `database-52*` 标明为概念 package / 文档内示例；YAML 与代码片段仍完整在 docs           |
| v0.9 源码路径 | 对照片段标明来自归档 v1，避免误读为当前 greenfield 树                                  |
| vault 双链    | §22 历史笔记改为标题列表；外链 URL 保留                                                |

除上表外，机制、红线、Core 边界、配置形状、Runtime/插件模型按 **docs ≡ vault 技术内容** 使用。

### 防漂移规则

1. 改设计只改 `docs/design/`（及必要时 PRD/glossary），再同步 Architecture、Issues、代码与 website。
2. Issue 与 website **链接** design 精确标题，不复制大段设计正文。
3. 不以 vault 为日常编辑面。若对照发现不一致：**以 docs 为准**。
4. 新增机制必须先有 design 段落，再开 Issue / 编码。

## 同步规则

- 改设计 → 更新对应 `design/*`（及必要时 PRD/glossary）→ 再改 Architecture / 代码 / website 相关页。
- 用户点名的绑定决策 → 写入相关 `docs/design/*` 小节（或 AGENTS 红线），**不**另起 constitution 目录。
- 读者向用法 → `website/`；SPA 开发细节 → `apps/*` README。

## 可选：vault 备份软链接

若本机 `Developer/ob-notes` 与 `Developer/work` 并列，可存在：

```text
docs/reference/BORA-统一配置与动态-Harness-设计.md → vault 历史长文
```

**非权威、只读对照。** 禁止经软链接写入 vault。日常只维护本仓 `docs/design/`。
