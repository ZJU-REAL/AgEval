# Spec 02 — nooa：多扩展点 provide/on 切换

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | in-progress |
| Completed | pending |
| Dependencies | [00](00-extension-registry-default-plan.md), [01](01-acp-default-providers-plan.md) |
| Decisions | [constitution §7.3–7.6](../constitution/2026-08-11-extension-api-and-registry.md)；任务程序分工 [§B.6](../constitution/2026-08-11-extension-api-and-registry.md) |

## User Story

作为 **机制 / Dataset 作者**，我可以在 **不修改 harness.py** 的前提下，用 profiles 的 `executor: nooa`（表示 **executor 槽** 选用 **nooa 插件对应该槽的 provide**）切换机制；**其它 binding 仍可让 executor 槽用 acp 的 provide**；lock 按 profile 分图。

## Acceptance

- [ ] **Success smoke：** journeys nooa 路径一条（完整命令写入本 Spec Docs 或 README）→ 可完成且可评分；lock `extension_bindings.<profile>.executor.plugin == nooa`（含 digest 若已装包）。
- [ ] **Expected failure：** 未 Ready / 缺 `options.agent` → 可诊断；provide 平局无显式 → fail closed。
- [ ] **Regression：** Spec 01 ACP smoke 仍过；harness 无强制 diff。
- [ ] **并存：** 同 profiles 下 `solver=nooa` 与另一 profile `executor=acp` 可同时配置；各自 session 调各自 graph（[constitution §7.6](../constitution/2026-08-11-extension-api-and-registry.md)）。
- [ ] **Baseline：** vendor+Dockerfile+`--set` 可跑，无统一 lock 图。
- [ ] **Engineering gates：** 相关测试。  
- [ ] **Docs：** 插件 vs `lib/agents`（链 [§B.6](../constitution/2026-08-11-extension-api-and-registry.md)）。

## Scope

- **Included：** nooa SPI 注册；profiles `executor: nooa`（槽选用 nooa 的 provide）；image_contribute → bake；lock 图；分 profile 与 acp 并存。  
- **Deferred：** Hub 分发 → [03](03-cli-plugin-lifecycle-plan.md)/[04](04-hub-plugin-package-kind-plan.md)（本 Spec 可用 path 装入 Registry）。

## 实现思路

### 必读决策

| 主题 | 链接 |
| --- | --- |
| 短绑定、不抄全槽 | [constitution §7.2–7.3](../constitution/2026-08-11-extension-api-and-registry.md) |
| lock 分 profile 图 | [constitution §7.4](../constitution/2026-08-11-extension-api-and-registry.md) |
| resolve 如何拿到正确方法 | [constitution §7.6](../constitution/2026-08-11-extension-api-and-registry.md) |
| 插件 vs task `lib/agents` | [constitution §B.6](../constitution/2026-08-11-extension-api-and-registry.md) |
| Registry/resolve 实现 | [Spec 00 实现思路](00-extension-registry-default-plan.md) |
| ACP 不被本 Spec 拆掉 | [Spec 01](01-acp-default-providers-plan.md) |

### nooa 贡献最小集

实现 `ExecutorSPI`，内部可复用现有 L1 JSONL + `bora_executor_nooa` worker 客户端逻辑（从 adapters/L1 路径迁或门面）。

| 槽 | 动作 |
| --- | --- |
| `executor` provide | `plugin_id="nooa"`；invoke 走 worker open/invoke/close |
| `image_contribute` | bake `nooa` + `bora-executor-nooa`（与现 journeys Dockerfile 意图对齐） |
| `trajectory_collect` | worker metadata / structured → 片段 |

`options.agent` / `options.method`：由 NooaExecutor 在 open 时读 `BindingIntent.options`，**不是** harness 解析。

### 注册方式

1. **开发/测试：** `register_nooa_contrib(registry)` 或从 cache 加载（对接 Spec 03 index）。  
2. **切换：** profiles 或 CLI：

```yaml
bindings:
  solver:
    executor: nooa
    options:
      agent: "lib.agents:JsonlAggAgent"
      method: "run"
```

resolve：见 Spec 00 / constitution §7.3——`executor: nooa` 只选槽上的贡献方，且要求 nooa 已 provide(executor)。**禁止** harness 分支 `if executor == "nooa"`。

### 与 ACP 并存（必测）

```yaml
bindings:
  solver:
    executor: nooa
    options: { agent: "lib.agents:…", method: "run" }
  user:
    executor: acp
    options: { entry: pi }
```

断言：

- `session("solver").extension_graph.providers["executor"]` → nooa  
- `session("user").extension_graph.providers["executor"]` → acp  
- 两次 invoke 不共享错误的 executor 实例

### Ready 与失败

| 条件 | 期望 |
| --- | --- |
| Recognition 有 nooa，镜像无 worker | prepare/open 失败，信息含 bake/Ready |
| 缺 options.agent | open 失败，稳定 error 子串可测 |
| 两插件同 priority provide executor 且无显式 | lock 或 resolve 阶段 conflict |

### 任务侧

- `lib/agents.py` 仍属 package（[§B.6](../constitution/2026-08-11-extension-api-and-registry.md)）。  
- 本 Spec 不删除 task-local Agent 类要求。

### 禁止

- 进程全局单例 executor。  
- 为切 nooa 改 harness 业务分支。  
- install 自动改 profiles（见 Spec 03 / §7.5）。

## Phases

- [ ] Phase 0：Nooa ExecutorSPI + 注册  
- [ ] Phase 1：profiles `executor:` 字段 + lock 图断言  
- [ ] Phase 2：Ready / agent / conflict 失败面  
- [ ] Phase 3：ACP 回归 + 双 binding 并存 + Acceptance  
