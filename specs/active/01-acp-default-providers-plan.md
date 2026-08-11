# Spec 01 — ACP：默认注册 + 专有 contribute（非全量插件包）

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | completed |
| Completed | 2026-08-11 |
| Dependencies | [00](00-extension-registry-default-plan.md) |
| Decisions | [constitution §4](../constitution/2026-08-11-extension-api-and-registry.md)；目录 [§7.1A `contrib/acp`](../constitution/2026-08-11-extension-api-and-registry.md)；调用链 [§7.6](../constitution/2026-08-11-extension-api-and-registry.md) |

## User Story

作为 **使用 ACP 的操作者**，我可以在 **不安装全量 ACP 外置插件包** 的前提下跑通公开 Attempt；通用管线为 **默认注册**，ACP 独有能力为 **first-party contrib**；lock 可区分 default 与 acp。

## Acceptance

- [x] **Success smoke：** lock 路径断言 `extension_bindings.*.executor.plugin == acp`（`bora lock examples/journeys --task terminal-jsonl-agg`）；run 仍走 graph 钉死的 ACP SPI（不要求 Hub 装 ACP 包）。完整 `bora run` 受本机 entry/API 约束，不在本 Spec 扩证据等级。
- [x] **Expected failure：** entry 缺失 → `acp_entry_required` fail closed，不静默换其它 executor。
- [x] **Regression：** Spec 00 机制仍在；task `harness.py` 无强制修改。
- [x] **Baseline：** ACP builtin，未按扩展点拆分。
- [x] **Engineering gates：** `tests/plugins/test_acp_nooa_contrib.py` + registry/lock 测试。
- [x] **Docs：** ACP = first-party contrib，非全量外置包（ARCHITECTURE Current 树）。
- [x] **结构证据：** `plugins/defaults/` 与 `plugins/contrib/acp/` 职责分离，见 §7.1A。

## Scope

- **Included：** 默认贡献；ACP `provide(executor)`、image/entry 贡献、协议侧 collect；主路径零 Hub ACP 包。  
- **Deferred：** nooa → [02](02-nooa-provide-switch-plan.md)；ACP 是否另发 `bora.plugin/1` → 非必须。

## 实现思路

### 必读决策

| 主题 | 链接 |
| --- | --- |
| 默认 vs ACP 专有、禁止全量 ACP 包 | [constitution §4](../constitution/2026-08-11-extension-api-and-registry.md) |
| 目录：`defaults/` vs `contrib/acp/` | [constitution §7.1A](../constitution/2026-08-11-extension-api-and-registry.md) |
| session 钉 graph 后 invoke | [constitution §7.6](../constitution/2026-08-11-extension-api-and-registry.md) |
| profiles 短绑定 | [constitution §7.3](../constitution/2026-08-11-extension-api-and-registry.md) |
| 平台 resolve/冲突（本 Spec 不重写） | [Spec 00 实现思路](00-extension-registry-default-plan.md) |

### 拆分清单（实现时填满注册）

**`plugins/defaults/`（plugin_id 建议 `"default"`）**

- L0 phase 钩子：默认 no-op 或只记 timing（若已有 phase_timing，接到现逻辑）。  
- L1：不含 ACP entry 的通用壳（透传现有 Dockerfile 基座行为）。  
- L2 multi：before/after 透传 `next(value)`。  
- L4：`trajectory_seal` 默认权威形状（现 evidence 写盘逻辑搬家至此，可被 replace_default）。  
- L5：cleanup warning 语义（cleanup 失败不撤销 score）。

**`plugins/contrib/acp/`（plugin_id 固定 `"acp"`）**

| 槽 | 贡献 |
| --- | --- |
| `executor` provide | 现有 AcpExecutor / ACP JSON-RPC 客户端路径，实现 `ExecutorSPI` |
| `image_contribute` | L1 官方 entry bake 声明（pi/codex/… 与现 Dockerfile/install-executors 对齐） |
| `trajectory_collect` on 或 provide | ACP 事件流 → 片段，供 seal 消费 |
| 其它 ACP 独有 | 仅放独有；能进 default 的不要塞 acp |

### 启动注册顺序

```text
register_defaults(registry)      # Spec 00
register_acp_contrib(registry)   # 本 Spec；plugin_id="acp"
# 默认 profiles executor: acp → resolve 选中 acp provide
```

### 与现有 `adapters/acp` 的迁移

1. **允许门面：** `bora.adapters.acp` 继续可 import，内部委托 `bora.plugins.contrib.acp`。  
2. **行为锚点：** Parent 仍唯一 ACP client；L1 `docker exec` stdio；`options.entry` 语义不变（见 design agent-service）。  
3. **禁止** 把 prepare→cleanup 整链搬进 acp 包。

### 默认 profiles 对齐

journeys 等现有 `executor: acp` + `options.entry: pi` 必须：

- resolve 后 `graph.providers["executor"]` 为 ACP SPI；  
- lock 记录 `plugin: acp`（或 default 链 + acp provide，以实际注册为准，**写进测试断言**）。

### 失败

- entry 不在镜像 / 未 bake：`open`/`invoke` fail closed，error 可测。  
- 禁止 fallback 到 openai-http 或 nooa。

### 回归清单

- `terminal-jsonl-agg` 默认 ACP 跑通（或仓库当前默认 smoke task，文档写死一条）。  
- `--set` entry 切换若原先支持则仍支持。  
- harness 文件 diff 为空（本 Spec 范围）。

### 禁止

- 文档或代码要求 `bora plugin install acp` 才能主路径。  
- harness 依赖 `contrib.acp` 类型。

## Phases

- [x] Phase 0：defaults 与 acp 贡献清单 + 注册（`plugins/contrib/acp`）  
- [x] Phase 1：invoke 走 graph（ParentAgentService 仅 graph provider）  
- [x] Phase 2：entry 缺失 fail closed + lock journeys smoke  
- [x] Phase 3：lock 字段断言 + ARCHITECTURE + Acceptance  

## Evidence

- `extension_bindings.solver.executor.plugin == acp` on journeys lock  
- Unit：`test_acp_entry_missing_fail_closed`、`test_acp_provide_selected_by_profile_executor`  

