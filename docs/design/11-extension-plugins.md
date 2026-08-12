# 11 — Extension points and mechanism plugins

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件与同目录其它 design 文档共同构成设计权威 |
| 摘要 | 固定扩展点 L0–L5、注册表 resolve/冲突、lock `extension_bindings`、外置 `bora.plugin/1`、Recognition ≠ Ready |

---

## 模型

扩展模型是 **宿主固定扩展点 + 注册表**（写法 B），不是继承整机 Runtime，也不是 pip entry-point 双轨。

| 角色 | 职责 |
| --- | --- |
| **扩展点（slots）** | Core 声明的稳定钩子 id；分 **multi（链）** 与 **provide（单赢家）** |
| **注册表** | `on` / `provide`；优先级；按 `plugin_id` 索引 |
| **resolve** | 显式绑定优先；未显式时比 priority；**并列 fail closed** |
| **插件** | 只向声明的扩展点贡献；不改 `harness.py` |
| **lock** | 写出完整 `extension_bindings`（图摘要 + source/priority/digest） |

### multi vs provide

| 类型 | 语义 | 例子 |
| --- | --- | --- |
| **multi** | 有序链，`(ctx, value, next)`；可改写或短路 | `before_agent_invoke`、`image_contribute` |
| **provide** | 单赢家 | `executor`、`env_action`、`trajectory_seal`、`evaluation_runtime` |

**反模式：** 插件不得堆积「声明式 command 行」让 Core 事后解释；handler 在控制点 **被 await**，持有 live `ctx`。

### 产品不变量

1. `profiles.executor`（及 `extensions` 显式绑定）选择 provide；**禁止** `resolve_executor` dual path / `bora.agent_executors` 旁路  
2. **nooa 等生态插件外置**（`plugins/` + install），不进 first-party bootstrap  
3. `bora plugin install` **只写本地 cache**（`$BORA_HOME/plugins`），**永不改写** profiles / task.yaml  
4. **Recognition ≠ Ready**：install 可见 ≠ L1 镜像可跑；Ready 来自 `image_contribute` bake  
5. PASS 只来自独立 evaluator；扩展链不得发明 PASS  
6. 凭据只经 scoped projection；不进 lock / evidence  

### Core vs 插件所有权

| 保留在 Core | 交给插件 | 共存 |
| --- | --- | --- |
| package `data/` → `seed_l1_workspace` | 旧 builtin + entry_point dual path | Core seed 后 plugin `after_prepare` / env / image_contribute |
| evaluator barrier / PASS | L1 Ready 靠 parent host SPI 冒充 | trajectory：Core 写盘；`trajectory_*` 扩展 fail-open（有意） |
| credential 投影 | Runtime 直接散落工厂 | plugins 只拿 scoped env |

固定顺序：**Core seed → 再 plugin chains**。

---

## 公开扩展点 L0–L5

权威 id 与 kind 见 `src/bora/plugins/slots.py`。分层：

| 层 | 代表槽 | 生产消费点 |
| --- | --- | --- |
| L0 | `before/after_prepare|run|evaluate|cleanup` | `application/extension_hooks` |
| L1 | `image_contribute`、`env_*`、`env_action` | prepare bake；env prepare/teardown + action_gate |
| L2 | `executor`、agent open/invoke/close、`normalize_agent_result` | `ParentAgentService` session 钉图 |
| L3 | `evaluation_input_contribute`、`evaluation_runtime`、`score_postprocess` | 评测前/后（fail closed；不得选 PASS 权威） |
| L4 | `trajectory_collect|enrich|seal`、`evidence_extra` | seal 写路径（collect/enrich fail-open） |
| L5 | `cleanup_actions`、`cleanup_report` | cleanup emit |

**生产 emit 图（摘要）：**

```text
open_session → resolve graph pin → before/after_agent_open
invoke       → before_agent_invoke → executor.invoke → after_agent_invoke
             → normalize_agent_result
             → seal: trajectory_collect → enrich → write trajectory.jsonl
                    → trajectory_seal → evidence_extra
close_session → before_agent_close → executor.close → after_agent_close

env prepare  → seed/health → env_prepare multi → env_inject → env_action provide
env teardown → env_teardown multi → EnvironmentManager.close

evaluate     → evaluation_input_contribute → evaluation_runtime
             → package evaluator → score_postprocess
```

公开槽必须有生产 emit **或** 在本文件 / ARCHITECTURE 明示非公开；禁止 silent dead public SPI。

---

## 包格式 `bora.plugin/1`

外置机制包（非 Dataset）：

- 根 `plugin.yaml`：`plugin_id`、`version`、`slots.provide` / `slots.on` + entry  
- 可选 `docker/Dockerfile.bake`（L1 Ready）  
- install：`bora plugin install <path|org/id@ver>` → `~/.bora/plugins`  
- Hub/Registry：`package_kind=plugin`；media type `application/vnd.bora.plugin.v1.tar+gzip`  
- Dataset 与 plugin **fail closed** 区分（Hub 列表过滤 / detail 拒绝混开）

### First-party vs 外置

| 来源 | 例子 |
| --- | --- |
| first-party contrib（bootstrap） | `acp`、`openai-http`、`mock` + `defaults` multi |
| 外置 install | `nooa`、`slot-probe`（仓库 `plugins/` 仅示例，不进 Core） |

---

## 配置与绑定

- Job binding 在 `profiles.yaml`：`executor` / `options` / `extensions`（binding 字段）  
- member `task.yaml` 只声明 role slot，禁止内联 binding  
- `bora lock` 解析每个 profile → `extension_bindings` 进 digest  
- 切换机制：**同一 harness**，改 profiles +（必要时）install，不改 harness 业务代码  

### nooa 绑定形状

```yaml
bindings:
  solver:
    executor: nooa
    options:
      agent: "lib.agents:JsonlAggAgent"  # package-local
      method: "run"
```

L1：bake 后 **in-container worker** 执行；parent host SPI 不是 L1 成功路径。

---

## CLI

| 命令 | 行为 |
| --- | --- |
| `bora plugin install` | 写 cache / index；可 registry 远程 |
| `bora plugin list` | 读 index |
| `bora plugin uninstall` | 可逆移除；不改 profiles |
| `bora plugin publish` | `package_kind=plugin` 上传 Registry |
| `bora plugin materialize-docs` | 显式拷贝 README/skills；非 silent |

---

## 与证据等级

文档与 Hub UI **不**升级 `runnable-mvp` / `isolated` / `real-benchmark-verified`。  
限定公开 smoke 仍见 `examples/README.md`；插件路径需对应 journey 证据后再宣称。

## 相关

- 结构地图：[`ARCHITECTURE.md`](../../ARCHITECTURE.md)（plugins 树、emit map）  
- Owner：[`09-owner-matrix-and-structure.md`](09-owner-matrix-and-structure.md)  
- Runtime Agent：[`05-runtime/agent-service.md`](05-runtime/agent-service.md)  
- 示例：`plugins/nooa`、`plugins/slot-probe`、`examples/journeys/profiles.nooa.yaml`、`examples/slot-probe/`  
- 交付跟踪：GitHub Issues（Epic 插件系统）
