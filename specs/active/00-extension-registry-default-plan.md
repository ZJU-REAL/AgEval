# Spec 00 — 扩展点注册表、默认注册与 lock 全图

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | completed |
| Completed | 2026-08-11 |
| Dependencies | none |
| Decisions | [constitution](../constitution/2026-08-11-extension-api-and-registry.md)（**§1–3 模型；§7 验收与目录/链路**） |

## User Story

作为 **BORA 运行时/操作者**，我可以在 `bora lock` / run 装配中让系统通过 **注册表** 解析 **L0–L5 全部公开扩展点** 的贡献（含 **默认注册**），应用 **显式绑定 > priority、平局 fail closed**，并在 **lock 中按 profile 展开完整扩展点图**，以便插件只挂固定扩展点、Job 可复盘。

## Acceptance

- [x] **Success smoke：** `uv run bora lock examples/journeys --task terminal-jsonl-agg` → 成功；lock 含按 binding/profile 分图的 `extension_bindings`（字段名可微调，语义见 [constitution §7.4](../constitution/2026-08-11-extension-api-and-registry.md)）。
- [x] **Expected failure：** 未注册槽 / 非法 provide → fail closed；同槽无显式绑定且 priority 平局 → fail closed。
- [x] **Regression：** 默认 profiles 下既有 ACP 装配不因注册表引入而 ERROR（session 仅走 graph；无 resolve_executor 双轨）。
- [x] **Baseline：** 无统一扩展点注册表；无 lock 扩展点全图。
- [x] **Engineering gates：** ruff / 相关 pytest（`tests/plugins` + config/runtime 回归）。
- [x] **Docs：** lock 字段与冲突规则；结构变 → ARCHITECTURE（Current 树含 `plugins/`）。
- [x] **结构证据：** [constitution §7.1A](../constitution/2026-08-11-extension-api-and-registry.md) 的 `plugins/` 分层落地（slots、registry、resolve、defaults）。

## Scope

- **Included：** 注册表 on/provide；冲突规则；链中间件（可改写）；默认可卸/替；L0–L5 默认注册；lifecycle/session emit + resolve；profiles `executor:` 字段展开为「槽选用插件 provide」；lock 完整图；调用链见 [constitution §7.6](../constitution/2026-08-11-extension-api-and-registry.md)。
- **Deferred：** ACP 专有 → [01](01-acp-default-providers-plan.md)；nooa → [02](02-nooa-provide-switch-plan.md)；CLI → [03](03-cli-plugin-lifecycle-plan.md)；Hub → [04](04-hub-plugin-package-kind-plan.md)。

## 实现思路

### 必读决策（勿重复发明）

| 主题 | 链接 |
| --- | --- |
| 扩展模型 B、链/单赢家、默认可卸、链可改写 | [constitution §1](../constitution/2026-08-11-extension-api-and-registry.md) |
| 冲突规则、profiles 短绑定、lock 真相 | [constitution §2](../constitution/2026-08-11-extension-api-and-registry.md) |
| L0–L5 全公开 | [constitution §3](../constitution/2026-08-11-extension-api-and-registry.md) |
| 目录树、cache、profiles/lock 形状、install 表、resolve 调用链、端到端验收句 | [constitution §7](../constitution/2026-08-11-extension-api-and-registry.md) 全文 |

### 代码落点（在 §7.1A 之上钉职责）

在 `src/bora/plugins/` 实现（与 [constitution §7.1A](../constitution/2026-08-11-extension-api-and-registry.md) 一致）：

| 文件 | 必须提供的 API / 行为 |
| --- | --- |
| `slots.py` | 全部公开 slot 常量；每个 slot 标注 `multi` 或 `provide`；未知 slot → resolve 失败 |
| `protocol.py` | `ExecutorSPI`：`async open/invoke/close`；`HookHandler`：`async (ctx, value, next) -> value`；`ImageContribute`：可合并的声明结构（list/dict，由 prepare 消费） |
| `registry.py` | `provide(slot, plugin_id, impl|factory, priority)`；`on(slot, plugin_id, handler|factory, priority)`；查询 API；重复注册策略文档化（同 plugin_id 覆盖须进 lock source） |
| `conflict.py` | 输入候选列表 + 显式绑定 → 唯一赢家或排序 chain；平局无显式 → 抛 `ExtensionConflictError` |
| `resolve.py` | `resolve(BindingIntent) -> ExtensionGraph`；见下算法 |
| `middleware.py` | 对 multi 槽按 chain 调 `next`；支持短路（不调 next） |
| `lock_bind.py` | `ExtensionGraph` → 可 JSON 序列化结构，挂到 lock 文档 |
| `defaults/` | 为 **每个** L0–L5 槽注册至少一条 default 贡献（可为 no-op / 透传 / 现有 Core 行为搬家） |

`BindingIntent` 最小字段：`profile_id`、`executor: str | None`、`options: dict`、`extensions: list[ExplicitBinding]`。  
`ExplicitBinding`：`slot`、`plugin`、`priority?`、`replace_default?`。

`ExtensionGraph` 最小字段：

- `providers: dict[slot, ProviderRef]`（provide 槽）
- `chains: dict[slot, list[HandlerRef]]`（multi 槽）
- `records: list[BindingRecord]`（供 lock：plugin、priority、source、digest、replaced_default）

`ProviderRef` / `HandlerRef` 持有 **已解析的可调用对象**（或 session 级 factory 结果），不是裸字符串。

### resolve 算法（实现伪码）

```text
function resolve(intent, registry):
  graph = empty ExtensionGraph
  for slot in ALL_PUBLIC_SLOTS:
    candidates = registry.candidates(slot)  # default + installed + first-party
    explicit = intent.extensions.filter(slot)
    if slot == "executor" and intent.executor:
      # 兼容字段：值 = plugin_id，语义 = 本槽选用该插件对 executor 的 provide
      # 不是「executor 概念等于 plugin」；须 registry 中该 plugin 已 provide(executor)
      explicit.append(ExplicitBinding(slot="executor", plugin=intent.executor,
                                      source="profile_executor_field"))
    if slot.kind == provide:
      winner = conflict.pick_one(candidates, explicit)  # 显式 > priority；平局 error
      graph.providers[slot] = materialize(winner)
      graph.records.append(...)
    else:  # multi
      chain = conflict.order_chain(candidates, explicit, replace_default flags)
      graph.chains[slot] = [materialize(c) for c in chain]
      graph.records.extend(...)
  return graph
```

`materialize`：若注册的是 factory，用 `intent.options` + profile 投影后的 env 构造；若是单例 SPI，直接用。失败 → fail closed。

### 接到现有 BORA 路径（文件级）

1. **Composition root / 启动**  
   调用 `register_defaults(registry)`。已装插件加载属 Spec 03；本 Spec 测试可用内存注册。

2. **`config/load_and_lock.py`（或 lock 写出口）**  
   对每个将进入 lock 的 `profile_id`：从 profiles 建 `BindingIntent` → `resolve` → `lock_bind` 写入 `extension_bindings[profile_id]`。  
   形状见 [constitution §7.4](../constitution/2026-08-11-extension-api-and-registry.md)。

3. **Agent session open（Agent Service / SDK 宿主侧）**  
   `graph = resolve(binding_of(profile_id))`  
   `session.extension_graph = graph`（**钉死**；见 §7.6）。  
   禁止使用「进程全局一个 executor」忽略 profile。

4. **invoke 热路径**  
   ```text
   g = session.extension_graph
   prompt = await run_chain(g, "before_agent_invoke", prompt)
   # open 若尚未 open：await g.providers["executor"].open(...)
   result = await g.providers["executor"].invoke(...)
   result = await run_chain(g, "after_agent_invoke", result)
   # normalize / trajectory_* 等同理按槽取 chain 或 provider
   ```

5. **lifecycle（application）**  
   prepare 前后、cleanup：emit L0/L1/L5 对应槽（merge `image_contribute` 声明交给现有 Docker/bake 管线）。

### profiles `executor:` 字段展开

见 [constitution §7.3](../constitution/2026-08-11-extension-api-and-registry.md)：

- `executor: nooa` = 「**扩展点 executor** 选用 **插件 nooa** 所 **provide** 的实现」。  
- 校验：nooa 必须已对 `executor` 做过 provide，否则 fail closed。  
- nooa 对其它槽的 on/provide 仍来自插件注册，**不必**在 profiles 抄全。  
- 与「插件改写/提供 executor 槽」同义；**不是** executor 与 plugin 两个概念绑死成一个。

### 错误类型（建议稳定字符串/kind）

| 条件 | kind / 行为 |
| --- | --- |
| 未知 slot | `unknown_extension_slot` |
| provide 平局 | `extension_conflict` |
| plugin_id 未注册 | `extension_plugin_not_found` |
| factory 失败 | `extension_materialize_failed` |

### 单测（最低集）

1. 仅 default → graph.providers["executor"] 为默认/acp 路径实现。  
2. 显式 binding 覆盖更低 priority 候选。  
3. 两候选同 priority、无显式 → 抛 conflict。  
4. `solver`/`user` 两个 intent resolve 结果互不污染（各有 graph）。  
5. lock_bind 输出含 source、replaced_default、priority。  
6. multi 链顺序 = 优先级升/降序（**在代码与文档中固定一种**：建议 **数值越小越先执行**，并在 README 写死）。

### 禁止

- harness/task `import` 具体插件类。  
- import 顺序决定赢家。  
- 要求 profiles 抄插件全槽。  
- 每次 invoke 无校验地 re-resolve 导致与 lock digest 不一致。

## Phases

- [x] Phase 0：slots/protocol/registry/conflict/resolve/defaults + 单测  
- [x] Phase 1：session open 钉 graph；invoke 走 graph（删除 resolve_executor 双轨）  
- [x] Phase 2：load_and_lock 写 extension_bindings  
- [x] Phase 3：lifecycle emit；失败 kind；ARCHITECTURE；Acceptance  

## Evidence

- Smoke：`uv run bora lock examples/journeys --task terminal-jsonl-agg` → `extension_bindings.solver.executor.plugin == acp`
- Unit：`uv run pytest tests/plugins tests/config -q`
- Host invoke：`before_agent_invoke` → graph executor → `after_agent_invoke`（ParentAgentService）
- Completion check（subagent）：PASS；follow-up：legacy `agent_registry.resolve_executor` 清理、L0 lifecycle emit 接到 application（非 Acceptance 阻塞）

## Completion

- Subagent 00：PASS（lifecycle application emit / residual resolve_executor 为 follow-up）
- Subagent 01：PASS  
- Subagent 02：PASS（L1 nooa bake e2e 诚实延后）


