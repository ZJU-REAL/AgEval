# design/ — 机制设计索引

本目录是 BORA **机制与红线**的设计权威（自包含）。读序、与 vault 对照、防漂移规则见上级 [docs/README.md](../README.md)。

## 文档原则

`docs/design` 写 **稳定设计方案**，不是项目进度板。

| 应写 | 不应写 |
| --- | --- |
| 机制契约、边界、红线、配置形状、owner | 「目前处于 xx 状态」「迁移完成前仍…」 |
| 设计内的非目标 / 明确不做 | Issue 勾选、证据等级日报 |
| 模块应有的结构 | 「Current residual 代码可能仍…」 |

实现是否跟上 → **GitHub Issues + 代码 + `examples/`**。  
结构地图（current vs target 树）→ [ARCHITECTURE.md](../../ARCHITECTURE.md)。

## 阅读顺序

```text
PRD + design/00          产品是什么、红线是什么
    ↓
design/01–04、06–09      Core / 包 / Harness / Capability / Owner
    ↓
design/05-runtime/*      Runtime 稳定机制（按运行链读）
    ↓
design/11                扩展点 / 机制插件（registry · lock · install · Ready）
    ↓
design/12                Hub Dataset draft/release · ACL · Leaderboard 完备性
    ↓
design/02 + 10           配置形状与示例对照
    ↓
ARCHITECTURE.md          代码放哪（结构，不是进度）
Issues                   增量交付与实现缺口
```

## 目录

| 文档 | 内容 |
| --- | --- |
| [00-overview-and-product.md](00-overview-and-product.md) | 产品目标、红线、可见性投影、背景与设计修正 |
| [01-bora-core.md](01-bora-core.md) | BORA Core 五组机制与模块布局 |
| [02-task-package-and-config.md](02-task-package-and-config.md) | Database / Task、`bora.yaml` / `task.yaml`、Config Core |
| [03-harness-layer.md](03-harness-layer.md) | Harness 层职责与结构 |
| [04-harness-core-sdk.md](04-harness-core-sdk.md) | Harness Core（SDK）详细设计 |
| [05-runtime/](05-runtime/) | **Runtime 子文**（Lifecycle / Provider / Agent Service / Env / Eval / Evidence / Campaign） |
| [05-runtime-core.md](05-runtime-core.md) | stub：指向 `05-runtime/`（保外链） |
| [06-capability-adapter-visibility.md](06-capability-adapter-visibility.md) | Capability、Adapter 插件、可见性 |
| [07-budget-evaluation-failure.md](07-budget-evaluation-failure.md) | Budget、Evaluation、失败语义 |
| [08-conversion-security-testing.md](08-conversion-security-testing.md) | 转换、测试、安全边界 |
| [09-owner-matrix-and-structure.md](09-owner-matrix-and-structure.md) | Owner 矩阵、决策检查表、目标结构 |
| [10-examples-database-52.md](10-examples-database-52.md) | 设计意图下的示例对照（非进度） |
| [11-extension-plugins.md](11-extension-plugins.md) | 扩展点 L0–L5、注册表、lock bindings、`bora.plugin/1`、Recognition ≠ L0 host-ready ≠ L1 bake-declared、`--probe` |
| [12-hub-dataset-and-leaderboard.md](12-hub-dataset-and-leaderboard.md) | Dataset draft/release、dataset ACL、Leaderboard 完备性、suite 插件出处、个人主页、chrome |

### Runtime 子文（执行链）

```text
lifecycle → provider-l1 → agent-service → environment → evaluation → evidence
                                                         ↘ campaign-suite
```

| 文件 | 内容 |
| --- | --- |
| [05-runtime/README.md](05-runtime/README.md) | Runtime 边界与索引 |
| [lifecycle.md](05-runtime/lifecycle.md) | Run / Trial / Attempt、外层状态机 |
| [provider-l1.md](05-runtime/provider-l1.md) | Provider、L1 镜像 BOM、multi-actor |
| [agent-service.md](05-runtime/agent-service.md) | **ACP + entry** coding-agent inlet、插件扩展 |
| [environment.md](05-runtime/environment.md) | Environment 契约 |
| [evaluation.md](05-runtime/evaluation.md) | barrier、Result 绑定 |
| [evidence.md](05-runtime/evidence.md) | Attempt evidence / trajectory |
| [campaign-suite.md](05-runtime/campaign-suite.md) | Campaign vs Suite |
