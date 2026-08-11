# Spec 03 — CLI 插件生命周期（装入注册表）

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | in-progress |
| Completed | pending |
| Dependencies | [00](00-extension-registry-default-plan.md) |
| Decisions | [constitution §2](../constitution/2026-08-11-extension-api-and-registry.md)；cache [§7.1B](../constitution/2026-08-11-extension-api-and-registry.md)；落盘 [§7.5](../constitution/2026-08-11-extension-api-and-registry.md) |

## User Story

作为 **本机操作者**，我可以用 `bora plugin install` 把 `bora.plugin/1` 装进本机 cache，更新 index，使 Recognition 增加；**不**自动改项目 profiles；skill 仅显式物化。

## Acceptance

- [ ] **Success smoke：** install fixture → [§7.1B](../constitution/2026-08-11-extension-api-and-registry.md) 路径与 `index.json` 存在；`plugin list` 可见；Recognition 认识 kind。  
- [ ] **Expected failure：** 坏包/缺 manifest → 非 0；无半套启用（原子回滚）。  
- [ ] **Regression：** 未 install 时 00/01 默认路径不变；**profiles.yaml 不被 install 修改**（[§7.5](../constitution/2026-08-11-extension-api-and-registry.md)）。  
- [ ] **Baseline：** 无 plugin CLI。  
- [ ] **Engineering gates：** CLI 单测；`BORA_HOME` 可指临时目录。  
- [ ] **Docs：** 落盘路径、不改 profiles、materialize 用法。  
- [ ] **落盘表：** [§7.5](../constitution/2026-08-11-extension-api-and-registry.md) 逐行满足。

## Scope

- **Included：** cache；install/list/uninstall；manifest → Registry；启动加载；可选 materialize-docs。  
- **Deferred：** Hub 远程 → [04](04-hub-plugin-package-kind-plan.md)；静默写 `.agents/skills` → **不做**。

## 实现思路

### 必读决策

| 主题 | 链接 |
| --- | --- |
| Hub+CLI 主路径、bora.plugin/1 | [constitution §2](../constitution/2026-08-11-extension-api-and-registry.md) |
| cache 目录树 | [constitution §7.1B](../constitution/2026-08-11-extension-api-and-registry.md) |
| 插件包形态 | [constitution §7.1C](../constitution/2026-08-11-extension-api-and-registry.md) |
| install 写/不写 | [constitution §7.5](../constitution/2026-08-11-extension-api-and-registry.md) |
| 配置分层（install ≠ 绑定） | [constitution §7.2](../constitution/2026-08-11-extension-api-and-registry.md) |
| Registry on/provide | [Spec 00 实现思路](00-extension-registry-default-plan.md) |

### 路径常量

```text
BORA_HOME = env BORA_HOME or ~/.bora
PLUGINS_ROOT = $BORA_HOME/plugins
INDEX = $PLUGINS_ROOT/index.json
PKG = $PLUGINS_ROOT/<plugin_id>/<version_or_digest>/
```

单测必须能 `BORA_HOME=tmp/...` 全隔离。

### index.json 最小 schema

```json
{
  "plugins": [
    {
      "plugin_id": "nooa",
      "version": "0.1.0",
      "digest": "sha256:…",
      "path": "nooa/0.1.0",
      "format": "bora.plugin/1",
      "slots_summary": { "provide": ["executor"], "on": [] }
    }
  ]
}
```

写 index：写临时文件 → `os.replace` 原子替换。

### plugin.yaml 最小字段

```yaml
format: bora.plugin/1
plugin_id: nooa
version: 0.1.0
slots:
  provide:
    - id: executor
      priority: 50
      entry: "pkg.factory:build_executor"   # module:attr factory() -> ExecutorSPI
  on:
    - id: before_agent_invoke
      priority: 20
      entry: "pkg.hooks:before_invoke"
```

`entry` 加载：把 `PKG` 加入 import 路径或按 wheel 布局；`factory(**kwargs)` 签名与 Spec 00 `materialize` 对齐。

### install 步骤

```text
1. 读源路径 plugin.yaml；format 校验
2. 计算目录 digest（文件树规范排序哈希，算法写进代码注释与测试）
3. 复制到 PKG（已存在同 digest → idempotent 成功）
4. 更新 index
5. 不修改 cwd 下 profiles/bora.yaml/task.yaml
6. 可选：--activate 不在本 Spec（绑定仍手写 profiles）
```

### list / uninstall

- list：读 index，打印 id/version/digest/slots_summary。  
- uninstall：删 PKG 目录 + 更新 index；**不**改 profiles（可能留下失效 binding → 下次 resolve `plugin_not_found`，可接受）。

### 进程加载（lock/run 启动）

```text
load_installed_plugins(registry):
  for p in index.plugins:
    load manifest from p.path
    for each slot entry: registry.provide/on(...)
```

在 Spec 00 的 `register_defaults` **之后** 调用。失败：单个坏插件 skip+警告 或 fail closed（**选 fail closed 更安全**，写进实现与测试）。

### materialize-docs

```text
bora plugin materialize-docs <plugin_id> --target <dir>
```

只拷贝/软链 README 与 skills/；默认 target 禁止隐式 `.agents/skills`。

### CLI 入口

- `src/bora/cli/cmd_plugin.py` + `bora plugin` 子命令组挂到 main。  
- help 文案写明：install 不管 binding；切换靠 profiles。

### 禁止

- install 改 Database 文件。  
- 产品文档以 pip 为主路径。

## Phases

- [ ] Phase 0：路径、index schema、manifest 模型  
- [ ] Phase 1：install/list/uninstall 原子性  
- [ ] Phase 2：lock/run 启动 load_installed_plugins  
- [ ] Phase 3：materialize-docs + 文档 + Acceptance  
