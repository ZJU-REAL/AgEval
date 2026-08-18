# 11 — Extension points and mechanism plugins

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件与同目录其它 design 文档共同构成设计权威 |
| 摘要 | 固定扩展点 L0–L5、注册表 resolve/冲突、lock `extension_bindings`、外置 `bora.plugin/1`、Recognition ≠ L0 host-ready ≠ L1 bake-declared、`--probe` |

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
4. **Recognition ≠ L0 host-ready ≠ L1 bake-declared**：install 可见 ≠ 本机 L0 SPI 可构造 ≠ 本 profile 会 bake。L0 host-ready 只执行插件声明的 `host_requires`（至少 `import:`）。L1 bake-declared 是本 profile `extensions` **选中**的 `image_contribute` 且已安装根有 `docker/Dockerfile.bake`。`executor:` 只选 `provide(executor)`，**不**暗示 bake / trajectory / 其它 `on:`。MULTI 链只含 first-party/default **加上** 本 profile `extensions` 点名的插件；已安装但未列入的外置插件不进链、不进镜像。绑定了已安装 executor 但未选中 contribute 或缺 bake 文件 → fail closed。Core **不**按插件名解释 bake token，也**不**维护 plugin-id → pip extra 表。官方 ACP 五 entry 仍在 `docker/attempt` 基座 bake-in。不要用「official org」跳过 bake。
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
| L1 | `image_contribute`、`home_overlay`、`env_*`、`env_action` | prepare bake；cred 后 / HOME 拷贝前；env prepare/teardown + action_gate |
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

home_overlay → Core default 建 cred 树 → nxt（插件写 HOME/workspace 文件）→ 拷入 actor HOME
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
- 可选 `host_requires`（L0 host SPI 构造前提；见下）  
- 可选 `plugin_requires`（本地 plugin cache 依赖；见下。与 `host_requires` 并列，不是同一列表）  
- 可选 `docker/Dockerfile.bake`（L1 bake-declared，须本 profile `extensions` 选中 `image_contribute`）  
- install：`bora plugin install <path|org/name@version>` → `~/.bora/plugins`；默认先装 `plugin_requires` 再装被请求的包  
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

「Official」是 **市场展示策略**，不是运行时门闩。默认 allowlist 是单个 Registry 常量（org slug `official`，与 `org-create` 小写规则一致）。可选覆盖只在 **Registry 进程**（如 `BORA_OFFICIAL_ORGS`）——不是前端 `VITE_*`，也不是 CLI→Registry 拉取。改 allowlist **不得**要求改 `plugins/nooa/plugin.yaml` 或 journeys profiles。比较时 casefold，避免 `Official` / `official` 漂移。allowlist 上的 slug **禁止自助 create / claim**；只有带 `admin` scope 的 token（启动时的 `BORA_REGISTRY_BOOTSTRAP_TOKEN`）能创建。成员由 admin 或 org owner 按 GitHub login 写入，对方不必在线。bootstrap token 留在运维手里，不发给 owner。

Core 槽 id（`executor`、`image_contribute`、…）仍归 Core。

### `host_requires`（插件声明，Core 只执行）

外置 executor 若 L0 需要宿主 Python extra 或插件缓存内文件，必须在 `plugin.yaml` **声明**。Core 不得解析插件源码 / `Dockerfile.bake` 推断依赖，也不得写 `if plugin_id == …` extra 表。

```yaml
format: bora.plugin/1
plugin_id: dsh
host_requires:
  - import: deepseek_harness   # importlib.util.find_spec；不 spawn、不联网
    hint: "uv sync --extra dsh"  # 操作者提示；Core 不执行
  - file: compositions/slim.cordis.yml  # 相对已安装插件根
```

| 规则 | 语义 |
| --- | --- |
| 条目允许键 | **allowlist**：`import`、`file`、`hint`。**未知键 fail closed**（`plugin_host_requires_invalid`） |
| 每条至少 | `import` 和/或 `file`（可同时有）；`hint` 可选字符串 |
| `import:` | `importlib.util.find_spec`；不 import 模块、不调用工厂、不 spawn |
| `file:` | 相对已安装插件根的正规文件存在 |
| 谁消费 | 仅 L0 路径（`provider.kind` 为 `local` / 省略）与 `bora executors.host_ready` |
| 谁不消费 | L1（`provider.kind: docker`）**不**要求 host extra |

未声明 `host_requires`：插件主张「无宿主 extra」。此时 `host_ready` 仍要求能经工厂到达 `describe()`（registry 持有的是 factory，不得因缺 binary PATH 默认 `true`）。既无声明又看不到 `describe()` → `host_ready: false`。

### `plugin_requires`（插件图，不是 host extra）

`host_requires` 只声明宿主 extra（import / 插件根内文件）。插件之间的依赖另写 **`plugin_requires`**。不要把 `plugin_id` 塞进 `host_requires`。

```yaml
format: bora.plugin/1
plugin_id: agent-skills
version: 0.1.0
plugin_requires:
  - plugin_id: home-files              # 短 id：只认 cache / 本地 sibling
  # - plugin_id: Official/home-files   # Hub 地址：才允许从 Hub 拉
    hint: "bora plugin install plugins/home-files"
```

| 规则 | 语义 |
| --- | --- |
| 条目允许键 | **allowlist**：`plugin_id`（必填）、`hint`（可选操作者字符串；Core 不执行）。未知键 → `plugin_requires_invalid` |
| `plugin_id` 语法 | 与 manifest `plugin_id` 相同：短 `name` **或** Hub `org/name`（`normalize_plugin_id`） |
| 满足条件 | 本地 cache 里存在 **恰好** 该 id 的已安装行。`Official/home-files` 与短 `home-files` **不是** 同一行 |
| 版本 | 任一已装版本即可。本增量不做 version range / pin |
| 绑定 | **不**把依赖自动写入 `extensions[]`。profiles 仍显式 opt-in |
| 省略 | 省略或 `[]` ≡ 今日单树安装 |

**解析只看该行声明的 `plugin_id`。禁止用正在安装的父插件 org 改写短 id**（装 `OrgA/foo` 且依赖写 `bar`，不得变成 `OrgA/bar`）。

| 声明的 `plugin_id` | 解析顺序（先命中先赢） |
| --- | --- |
| 短 `name`（无 `/`） | (1) cache 已有 `name` → skip。(2) 仅当 install **源是本地目录**：sibling `<source.parent>/<name>/` 且其 manifest `plugin_id` 就是 `name`。(3) 否则 fail closed。**短 id 永不访问 Hub** |
| Hub `org/name` | (1) cache 已有 `org/name` → skip。(2) 拉该 **精确** Hub 包 `org/name` 的最新已发布 plugin release。(3) 否则 fail closed。不查 sibling |

`bora plugin install <source>` **默认传递**：先装 `plugin_requires`，再装被请求的包。本增量无 `--no-deps`。成功 JSON 列出被请求的包以及每个已装或已在 cache 的依赖。

其它语义：

- 环（`A → B → A`）在 install **和** lock / materialize fail closed  
- `bora plugin uninstall` **不**卸依赖  
- 依赖装失败 → 被请求的包 **不**写入 index（无部分行）  
- `bora plugin list` / `bora executors`：每个已装插件报告 `plugin_requires` 是否满足；不满足 → 不是 host-ready  
- `bora lock` / materialize：本 profile `extensions` 点名的每个插件，其 `plugin_requires` 必须已装（exact id）；否则 fail closed  
- materialize 插件 P 时，先把它声明的每个依赖的包根与 `src/` 放上 `sys.path`，再 import P 的 entry  

外置 `plugins/agent-skills` 是 `home_overlay` 的 dest 展开消费者：声明 `plugin_requires: [{plugin_id: home-files}]`（仓内短 id），调用 `home-files` 的 copy helper，不另造复制引擎。Hub 发布该插件时必须把依赖写成 `<org>/home-files`。authoring 面在插件 README。

### 三级就绪

| 等级 | 含义 | 来源 |
| --- | --- | --- |
| **Recognition** | 本机识别到 `provide(executor)` | `bora plugin install` / `plugin list` / `executors.supported` / lock `extension_bindings` |
| **L0 host-ready** | 宿主可构造 host SPI | 已安装 + 声明的 `host_requires` 全满足（或无声明且 `describe()` 可达）**且** `plugin_requires` 全满足 |
| **L1 bake-declared** | **本 profile** 会走 contribute bake | `extensions` 选中 `image_contribute` 且已安装根有 `docker/Dockerfile.bake` |

`bora executors.host_ready` = **L0 host-ready**（无 package，故不看 `extensions`）。`plugin_requires` 是 cache 图，L0 与 L1 `--probe` 都检查。`l1_bake_declared` 在 inventory 上只表示插件 **具备** bake 文件 + 槽；`--probe` 的 L1 就绪还要求本 profile `extensions` 选中了 contribute。不得对插件 PATH 探测 wheel 内二进制（如 `dsh-jsonrpc-agent`）来代替 `host_requires`。

### First-party vs 外置

| 来源 | 例子 |
| --- | --- |
| first-party contrib（bootstrap） | `acp`、`openai-http`、`mock` + `default` multi |
| 外置 install | `nooa`、`dsh`、`slot-probe`（仓库 `plugins/` 仅示例，不进 Core） |

---

## 配置与绑定

- Job binding 在 `profiles.yaml`：`executor` / `extensions` / 可选 `overlays`（binding 字段）；选择按 **profile（role）**，不是 task 级插件列表  
- 插件 knobs 只写在 **`extensions[]` 行上的 `options`**。`executor:` 只选 `provide(executor)`。  
- Profile 级 `options` **不是**插件输入（无 dual-read、无回落）。  
- member `task.yaml` 只声明 role slot，禁止内联 binding  
- `bora lock` 解析每个 profile → `extension_bindings` 进 digest（快照，不是选择器）  
- 切换机制：**同一 harness**，改 profiles +（必要时）install，不改 harness 业务代码  

### 每插件 `extensions[].options`

`executor:` 不携带插件 knobs。每个插件只读本行 `options`。工厂与 `on` handler 物化时只拿到该行 map。`options` 对 Core 是**不透明 map**。

plaza 发布树只来自 binding 级 `overlays:`（见 [02](02-task-package-and-config.md)）。Core **不得**遍历 `extensions[].options` 寻找 `src`（或任何路径形键）来构造、补全或校验该列表。不同插件的路径键名不同；有的 `src` 根本不是 overlay 文件。本增量接受 `overlays:` 与插件实际复制集之间的漂移，Core 不调和。`home_overlay` 运行时仍只按该插件自己的 `src` 拷贝。

```yaml
executor: acp
extensions:
  - plugin: acp
    options:
      entry: opencode
  - plugin: home-files
    options:
      files:
        - src: overlays/opencode.litellm.json
          dest: .config/opencode/opencode.json
          dest_root: home
  - plugin: dsh
    options:
      composition: slim
```

`--set /bindings/<role>/options/<key>` 写到 **该 role 的 executor 插件** 行（没有则补一行 `- plugin: <executor>`）。不能用同一指针表达非 executor 行（如 `home-files` 的 `files`）；那些只写 YAML。

### `home_overlay`（L1 multi；L0 在 Attempt HOME 存在后同样 emit）

插在 **cred 投影之后、actor HOME 拷贝之前**。不是 `after_prepare`（后者仍在选镜像 / bake 旁），也不是 `env_inject`。

Core default（低 priority，先跑）：建 cred 树（今日 allowlist）；把 `package_root` / `workspace_root` / `cred_root` 放上 `ctx`/`value`；`hook_home_overlay` 还把本 lock 全部 ACP `options.entry` 收集为 `value.acp_entries`（插件不读 sibling `acp` 行）；`await nxt(value)`；再把 `cred_root/home_overlay/.` 拷进 actor `$HOME/`，并完成今日 `prepare_agent_targets` 的其余步骤。插件只在 `nxt` 里写文件，不调 Docker，不发明 PASS。L0 不得写用户真 `~`。`plugins/agent-skills` 只展开 dest，复制仍走 `home-files`。

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
5. `executor:` **不**隐含 `image_contribute`。ACP 的 `entry` 写在 `- plugin: acp` 的 `options`；不再写 profile 级 `options`。  
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
        options:
          agent: "lib.agents:JsonlAggAgent"  # package-local nooa.Agent
          method: "run"
    model: openai/glm-5.2
    api_key: ${litellm_api_key}          # ${ENV_NAME} locator；值不进 lock
    # base_url: ${litellm_base_url}   # 可选；字面 URL 或 ${ENV_NAME}
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
| `bora plugin install` | 写 cache / index；可 registry 远程。默认先解析并安装 `plugin_requires`（短 id = sibling/cache；`org/name` = Hub 精确地址） |
| `bora plugin list` | 读 index；报告每包 `plugin_requires` 是否满足 |
| `bora plugin uninstall` | 可逆移除；不改 profiles |
| `bora plugin publish` | `package_kind=plugin` 上传 Registry |
| `bora plugin materialize-docs` | 显式拷贝 README/skills；非 silent |
| `bora lock … --probe` / `bora run … --probe` | 绑定感知的本机可行性探针（下节）；不是新动词 |
| `bora executors` | Recognition ∪ L0 host-ready ∪ `l1_bake_declared`；`execution_mode` 来自 `describe()` |

### `--probe`（机器可行性，不是 Attempt plan）

操作者在 `bora run` 前问：给定 Database + profiles + `provider.kind`，**这条已选路径**在本机能否开工。探针：

- 挂在已有命令上（`--probe`），**不**新增 `bora dry-run` / `bora preview`
- 读与 `lock`/`run` 相同的输入（package、`--task`、`--profiles`、`--set`）
- 按 **`provider.kind`** 分支，不按 plugin id
- **不** invoke Agent、**不** `docker build` / bake、**不** spawn 厂商运行时
- **不**把探针结果写入 lock digest / `config_fingerprint`；无 `--probe` 的 `bora lock` 行为不变
- 选中路径不满足 → 非零退出；仍打印 plan + checks（配置错误仍走 lock 的 exit 2）
- `BORA_OFFLINE_AGENT=1` 记入报告；探针仍不 spawn
- 凭据只报 **locator 名是否存在**；值永不进探针 JSON

#### L0（`provider.kind` 为 `local` / 省略）

对每个绑定的**外置** executor：

1. 插件已安装（Recognition）
2. 每条 `host_requires` 在宿主上满足
3. profile / `describe()` 声明的 credential locator **名**在 env 中存在（只查名）
4. 声明的 `file:` 在已安装插件缓存中存在

另外：走本 profile `extensions` **全部**已绑定插件（不只是 executor）。新检查：`plugin_installed`、`plugin_requires`（cache 图；缺行 → `ready: false`）。

缺 `import` → 类型化 miss（如 `host_import: missing`）+ 插件 `hint`。

#### L1（`provider.kind: docker`）

**不**要求 host extra（`host_requires.import` / `.file` 仍跳过）。检查：

1. 插件已安装
2. 本 profile `extensions` 选中了 `image_contribute`，且 `Dockerfile.bake` 存在
3. Docker daemon 可达（`BORA_SKIP_DOCKER=1` 视为不可达）
4. credential locator **名**存在（parent 投影需要）
5. 与 L0 相同：走全部已绑定 extension 插件的 `plugin_installed` / `plugin_requires`（这是 plugin cache，不是 host extra）

`executor:` 单独不够。绑定了已安装外置 executor 但未在 `extensions` 点名 contribute → 探针 **不 ready**（与生产 fail closed 一致）。ACP-only（无 `extensions`）不要求 bake；官方 `FROM`-only 包复用 `bora-attempt:l1`。

宿主没有 vendor extra、但 docker 任务 **选中** 了该插件的 contribute：只要 bake 文件 + Docker + locator 在，探针 **ready**。

#### `bora executors`（无 package，无 `provider.kind`）

- 不得因「已安装 / 无 PATH 候选」默认 `host_ready: true`
- 经工厂到达 `describe()`（registry 存的是 factory，不是 SPI 实例）；不得 PATH 探测 wheel 二进制
- `host_ready` = L0 host SPI 可构造
- `l1_bake_declared` 单独给出
- `execution_mode` 在 `describe()` 已发布时取其值，否则 `unknown`

---

## 与证据等级

文档与 Hub UI **不**升级 `runnable-mvp` / `isolated` / `real-benchmark-verified`。  
限定公开 smoke 仍见 `examples/README.md`；插件路径需对应 journey 证据后再宣称。

## 相关

- 结构地图：[`ARCHITECTURE.md`](../../ARCHITECTURE.md)（plugins 树、emit map）  
- Owner：[`09-owner-matrix-and-structure.md`](09-owner-matrix-and-structure.md)  
- Runtime Agent：[`05-runtime/agent-service.md`](05-runtime/agent-service.md)  
- 示例：`plugins/nooa`、`plugins/dsh`（`options.permission` 为插件自有键，非新 slot）、`plugins/home-files`（`on: home_overlay` 复制原语）、`plugins/agent-skills`（`home_overlay` dest 展开，`plugin_requires: home-files`）、`plugins/slot-probe`、`examples/journeys/profiles.nooa.yaml`、`examples/journeys/profiles.dsh.yaml`、`examples/journeys/profiles.dsh.read-only.yaml`、`examples/slot-probe/`  
- 交付跟踪：GitHub Issues（Epic 插件系统）
