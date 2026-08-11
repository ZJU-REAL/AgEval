# specs/ — Hub 插件与扩展点系统（SDD 工作区）

本目录是 **本主题** 的 Spec-Driven Delivery 工作区。

> 全仓权威仍为根 [AGENTS.md](../AGENTS.md)、[docs/design/](../docs/design/)、[ARCHITECTURE.md](../ARCHITECTURE.md)。  
> **本主题** 决策：[constitution/](constitution/)；增量：[active/](active/)。  
> **开发基线：`canary`**（从 canary 开分支、合回 canary）。  
> **无** ROADMAP。交付按 Active Spec **一口气完成**（非分期上线）。

## 目录

| 路径 | 用途 |
| --- | --- |
| [constitution/](constitution/) | 长期决策、背景与不变量 |
| [active/](active/) | 实现 Spec（00–04） |
| [BLOCKED.md](BLOCKED.md) | 执行期审计（最新在上） |

## 权威顺序（本主题）

```text
docs/design/* + ARCHITECTURE.md
  → specs/constitution/*
  → specs/active/*
  → 代码 + 公开 smoke
```

## 必读顺序

1. [ARCHITECTURE.md](../ARCHITECTURE.md)  
2. [docs/design/05-runtime/](../docs/design/05-runtime/)  
3. [constitution/2026-08-11-extension-api-and-registry.md](constitution/2026-08-11-extension-api-and-registry.md)（**终态决策 + §7 验收证据**）  
4. 当前 Active Spec 的 User Story + Acceptance + **实现思路**  

## 不变量（摘要 · 终态）

详见 constitution。摘要：

- 扩展模型 = **固定扩展点 + 注册表**（链 multi / 单赢家 provide），非 harness 子类化整条 Runtime。  
- 宿主包：**`src/bora/plugins/`**；安装 cache：**`~/.bora/plugins/`**（第三方不进主仓业务树）。  
- **L0–L5 全部公开**；L3 改评测语义必须完整进 lock。  
- **链槽** 中间件可改写 prompt/result；**默认贡献可被合法卸/替**（须进 lock）。  
- 冲突：**显式绑定 > priority**；平局 fail closed。  
- 绑定：**扩展 profiles**；真相 = **lock 完整扩展点图**。  
- 插件包：**`bora.plugin/1`** + manifest 声明 slots。  
- 默认注册保证仅装 BORA 时 ACP 主路径可跑；**非**全量 ACP 外置包。  
- harness 机制无关；Recognition ≠ Ready；主分发 Hub + `bora` CLI。  

## Active Spec 地图

| Spec | 主题 |
| --- | --- |
| [00](active/00-extension-registry-default-plan.md) | 注册表、默认注册、冲突、lock 全图、L0–L5 接线 |
| [01](active/01-acp-default-providers-plan.md) | ACP 默认/专有 contribute |
| [02](active/02-nooa-provide-switch-plan.md) | nooa provide/on 切换 |
| [03](active/03-cli-plugin-lifecycle-plan.md) | CLI 安装/列表 → 注册表 |
| [04](active/04-hub-plugin-package-kind-plan.md) | Hub `bora.plugin/1` |

## 命名与状态

- Active Spec：`active/NN-<短主题>-plan.md`  
- 状态：`in-progress` | `completed` | `cancelled`  

## 校验

```bash
python3 ~/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py .
```

## SDD

`$spec-driven-delivery` skill。
