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
4. **Recognition ≠ Ready**：install 可见 ≠ L1 镜像可跑；Ready 来自本 profile `extensions` 选中的 `image_contribute` bake。`executor:` 只选 `provide(executor)`，**不**暗示 bake / trajectory / 其它 `on:`。MULTI 链只含 first-party/default **加上** 本 profile `extensions` 点名的插件；已安装但未列入的外置插件不进链、不进镜像。绑定了已安装 executor 但未选中 contribute 或缺 bake 文件 → fail closed。Core **不**按插件名解释 bake token。官方 ACP 五 entry 仍在 `docker/attempt` 基座 bake-in。不要用「official org」跳过 bake。
5. PASS 只来自独立 evaluator；扩展链不得发明 PASS  
6. 凭据只经 scoped projection；不进 lock / evidence  

### Core vs 插件所有权

| 保留在 Core | 交给插件 | 共存 |
| --- | --- | --- |
| package `data/` → `seed_l1_workspace` | 旧 builtin + entry_point dual path | Core seed 后 plugin `after_prepare` / env / image_contribute |
| evaluator barrier / PASS；层 C `trajectory.jsonl` writer | L1 Ready 靠 parent host SPI 冒充；ACP-shaped `AgentResult.events` 伪装 | 层 B：adapter 映 `bora.trajectory.event/1`；`trajectory_*` 扩展 fail-open（有意） |
| credential 投影 | Runtime 直接散落工厂 | plugins 只拿 scoped env |

固定顺序：**Core seed → 再 plugin chains**。

---

## 公开扩展点 L0–L5

权威 id 与 kind 见 `src/bora/plugins/slots.py`。分层：

| 层 | 代表槽 | 生产消费点 |
| --- | --- | --- |
| L0 | `before/after_prepare|run|evaluate|cleanup` | `application/extension_hooks` |
| L1 | `image_contribute`、`env_*`、`env_action` | prepare bake；env prepare/teardown + action_gate |
| L2 | `executor`、agent open/invoke/close、`normalize_agent_result` | `ParentAgentService` session 钉图。L1 用 Core `TargetPlacement` + SPI `bind_to_target`；禁止 Core `if kind == …` 重建 executor |
| L3 | `evaluation_input_contribute`、`evaluation_runtime`、`score_postprocess` | 评测前/后（fail closed；不得选 PASS 权威） |
| L4 | `trajectory_collect|enrich|seal`、`evidence_extra` | seal 写路径（collect/enrich fail-open）。collect 可补层 B 事件；**不得**让插件直接写层 C 行，也不得再产出 ACP `session_update` 伪装 |
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
- install：`bora plugin install <path|org/name@version>` → `~/.bora/plugins`  
- Hub/Registry：`package_kind=plugin`；media type `application/vnd.bora.plugin.v1.tar+gzip`  
- Dataset 与 plugin **fail closed** 区分（Hub 列表过滤 / detail 拒绝混开）

### 两套地址：本地短 id 与 Hub 地址

同一包可以有 **本地 id** 和 **Hub 地址**。这是预期，不是缺陷。一份 profiles **不能**把两种地址混用于同一次安装。绑定只认 **`plugin_id`**，不认 `ExecutorSPI.kind`。两个安装不得共享同一 `plugin_id`（后写覆盖）。不要另设 `org-id` 字段。

| 动作 | 操作者写的 / index 存的 id |
| --- | --- |
| 路径安装 `bora plugin install plugins/nooa` | `plugin.yaml` **短** id：`nooa`。不访问 Registry。 |
| 仓内 first-party contrib（bootstrap） | 短 id：`acp`、`openai-http`、`mock`（+ `default` multi）。不经 install。 |
| `profiles.yaml` / `bora lock` / `bora run` | **恰好**本地 index（或 bootstrap）里的 id。路径安装后写 `executor: nooa`。 |
| `bora plugin publish --org Official` | Hub 包地址 **`Official/nooa`**。若 `plugin.yaml` 已是 `org/name`，`--org` 必须等于该前缀，否则拒绝。短 id → 拼接 `{org}/{plugin_id}`。 |
| `bora plugin install Official/nooa@version` | 本地 index 记录 **Hub** id `Official/nooa`，以及 version 与 digest。该 cache 行的 profiles 写 `executor: Official/nooa`。 |
| Hub 列表 / 详情 chip | Registry 在 **上传 org** 属于官方 org allowlist 时设 `official: true`。前端只渲染该布尔。 |

`bora lock` / `bora run` / 路径 `bora plugin install` **只**从 bootstrap ∪ 本地 index resolve；缺绑定 id → fail closed。**不**问插件是否 official，**不**调 Registry，**不**用环境变量把 `nooa` 改写成 `${OFFICIAL_ORG}/nooa`（lock digest 不得随 env 漂移）。路径安装不需要凭据或 Registry URL。

「Official」是 **市场展示策略**，不是运行时门闩。默认 allowlist 是单个 Registry 常量（org slug `official`，与 `org-create` 小写规则一致）。可选覆盖只在 **Registry 进程**（如 `BORA_OFFICIAL_ORGS`）——不是前端 `VITE_*`，也不是 CLI→Registry 拉取。改 allowlist **不得**要求改 `plugins/nooa/plugin.yaml` 或 journeys profiles。比较时 casefold，避免 `Official` / `official` 漂移。

Core 槽 id（`executor`、`image_contribute`、…）仍归 Core。

### First-party vs 外置

| 来源 | 例子 |
| --- | --- |
| first-party contrib（bootstrap） | `acp`、`openai-http`、`mock` + `default` multi |
| 外置 install | `nooa`、`dsh`、`slot-probe`（仓库 `plugins/` 仅示例，不进 Core） |

---

## 配置与绑定

- Job binding 在 `profiles.yaml`：`executor` / `options` / `extensions`（binding 字段）；选择按 **profile（role）**，不是 task 级插件列表  
- member `task.yaml` 只声明 role slot，禁止内联 binding  
- `bora lock` 解析每个 profile → `extension_bindings` 进 digest（快照，不是选择器）  
- 切换机制：**同一 harness**，改 profiles +（必要时）install，不改 harness 业务代码  

### `extensions` 按 profile 显式 opt-in

字段名保持 **`extensions`**。未列入的已安装插件不进入 MULTI 链、不 bake。Hub 安装后同一行写 Hub id（`Official/nooa`，…）。

```yaml
bindings:
  planner:
    executor: nooa                 # 只选 provide(executor)；不暗示 bake
    extensions:
      - plugin: nooa               # 该插件登记的全部槽（provide + on）
  reviewer:
    executor: dsh
    extensions:
      - plugin: dsh
        slots: [image_contribute]  # 只开列出的槽
      # 单槽写法（与历史上 {slot, plugin} 同义）：
      # - slot: trajectory_collect
      #   plugin: dsh
```

规则：

1. 省略 `slots` → 打开该插件已登记的每一个槽（`provide` + `on`）。  
2. `slots: [...]` → 只开列出的槽；未知槽或该插件未登记 → fail closed。  
3. `{slot, plugin}` → 恰好那一个槽。  
4. MULTI 链 **只**含本 profile `extensions` 点名的项。已安装但未列入的插件不进链、不进镜像。  
5. `executor:` **不**隐含 `image_contribute`。纯 ACP profile 省略 `extensions`。  
6. 绑定了**已安装** executor 但未选中 `image_contribute`（或缺 bake 文件）→ L1 fail closed。  
7. 同一 job 里不同 role 可独立绑定不同插件。  
8. 省略 `executor:` 时，若某条 `- plugin: …`（全槽）含该插件的 executor provide，可用它补上；两套都写时以 `executor:` 为准。

### nooa 绑定形状

外置插件对接 [NVIDIA-labs OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents)：用 profile 的 `model` / `base_url` / `api_key`（env locator）构造 `get_llm_client(...)`，再 `AgentClass(llm=...)` 调用包内 generation method。  
`options.agent` 应为 package-local **`nooa.Agent` 子类**（确定性 plain class 仅用于 slot-probe 等无 LLM 探针）。

```yaml
bindings:
  solver:
    executor: nooa
    extensions:
      - plugin: nooa
    model: openai/glm-5.2
    api_key: litellm_api_key          # env locator；值不进 lock
    # base_url: https://…/v1          # 可选；否则回落 litellm_base_url / OPENAI_BASE_URL
    options:
      agent: "lib.agents:JsonlAggAgent"  # package-local nooa.Agent
      method: "run"
```

L1：bake 安装 `nooa` + **in-container worker**；parent 把 model/base_url/密钥投影进 worker；host SPI 不是 L1 成功路径。

### 官方 ACP 镜像（不另打 `bora-pkg`）

下列条件**同时**成立时，prepare **不** `buildx --load` package 标签；Attempt 镜像就是已有官方 `bora-attempt:l1`：

- 每个已绑定 profile 都是 first-party `executor: acp`（无已安装/外置 executor）；  
- 选中的 `extensions` 不要求 `image_contribute` bake；  
- package Dockerfile 相对官方基座是空操作（今天：仅 `FROM bora-attempt:l1`，无 `COPY` / `RUN` / 其它层）。

Dockerfile 另有文件或其它 `FROM`，或任一选中扩展要 bake，仍走 `bora-pkg:{content}`（+ bake 后缀）。evidence 仍记 `image_digest`。`bora-attempt:l1` 的 hash 规则不变。

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
- 示例：`plugins/nooa`、`plugins/dsh`（`options.permission` 为插件自有键，非新 slot）、`plugins/slot-probe`、`examples/journeys/profiles.nooa.yaml`、`examples/journeys/profiles.dsh.yaml`、`examples/journeys/profiles.dsh.read-only.yaml`、`examples/slot-probe/`  
- 交付跟踪：GitHub Issues（Epic 插件系统）
