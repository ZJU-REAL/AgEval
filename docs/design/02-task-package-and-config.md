# 02 — Database、Task 与 Config Core

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 交付单元 Database、成员 Task、`task.yaml`、`load_and_lock`、配置对象与校验。 |

---

## Core 的输入：Task Package

> **交付单元 = Database。** Task Package 指 Database 下的**成员**（`tasks/<task_id>/` + `task.yaml`）。根 `bora.yaml` 仅为 Database schema，不是 task 执行契约。

### 交付单元

**规范交付与分发单位是 Database（suite）**，不是散落的单 task 目录。Task 是 Database 的成员。

| 层级 | 配置文件 | 位置 | Schema | 职责 |
| --- | --- | --- | --- | --- |
| Database | **`bora.yaml`** | **仅** Database 根 | `bora.database/1` | identity / version / 成员定位 / 可选 suite 调度默认 |
| Task | **`task.yaml`** | `tasks/<task_id>/` | `bora.task/1` | harness / evaluator / provider / limits / profiles… |

二者 **schema 不同**，禁止混用同一文档模型。CLI 路径参数始终是 **Database 根**；`--task <id>` 选择成员。Config 路径：

```text
database_root
  → load_database_manifest (bora.yaml)
  → resolve_task → tasks/<id>/task.yaml
  → load Database profiles.yaml (job binding defaults)
  → load_and_lock(task_dir, task_id, profile_bindings=…) → LockedTaskConfig
```

推荐布局：

```text
my-database/                      # Database 根（CLI path）
├── bora.yaml                     # format: bora.database/1
├── profiles.yaml                 # job binding 默认（role id → entry/model/locator；#59）
├── env.example                   # 文档化 credential locator 名（无密钥）
├── .env                          # 本机密钥（gitignore；永不 publish/upload）
├── README.md                     # suite 级说明（可选）
├── shared/                       # 可选；跨 task 共享（#65；见下节）
│   ├── lib/                      # Harness/Evaluator import only
│   ├── assets/                   # 只读领域数据（代码路径读取）
│   └── README.md
└── tasks/
    ├── task-a/
    │   ├── task.yaml             # format: bora.task/1；角色槽 + intent；无 entry/model
    │   ├── harness.py
    │   ├── evaluator.py
    │   ├── prompts/
    │   ├── schemas/
    │   ├── environment/
    │   ├── evaluation/
    │   ├── data/
    │   ├── lib/
    │   ├── upstream/
    │   └── solution/
    └── task-b/
        └── …
```

Database 根 `bora.yaml` 最小字段（字段名冻结）：

```yaml
format: bora.database/1
database_id: example/demo-suite   # 字符集见下；与 version 组成 release 坐标
version: "0.1.0"
tasks:
  root: tasks
# 可选 defaults 仅 suite 调度键，v1 白名单：max_concurrent_tasks
```

`database_id` **不**参与 PASS；只服务 publish / resolve / cache / evidence 溯源。  
**`database_id` 字符集（v1 冻结）：** 匹配 `^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$`（单字符 id 允许单独 `[a-z0-9]`）；长度 1–128；大小写敏感（规范写法全小写）；禁止 `..`、连续 `//`、前导/尾随 `/`；推荐 `org/name` 风格。非法 id → manifest load **fail closed**。  
`defaults` **禁止**携带 limits / provider / harness / evaluation 等 task 执行契约（避免与成员 `task.yaml` 歧义）。

成员 `task.yaml` 与 `harness.py` 共同定义可运行的 task：

- `task.yaml` 给出完整、集中、可比较的执行与评测配置；
- `harness.py` 解释参数并运行工作流；
- `evaluator.py` 拥有 task-local truth 入口；
- `prompts/`、`schemas/`、`data/`、`environment/`、`evaluation/` 按角色保存输入与资产；
- `lib/` 承载仅被 harness / evaluator import 的 package-local 支撑代码。

目录名 **必须** 等于 `task.yaml` 内 `task_id`；否则 fail closed。零成员 Database fail closed。

本文用概念 package `database-52-mvp/` 展示成员级默认路径，用 `database-52/` 展开更多 service 与 workspace 细节。两者的设计内容均在本目录文档中完整给出；v2 greenfield 仓库当前不要求存在这两个示意目录。仓内公开 examples 为三个 Database：`examples/core`、`examples/journeys`、`examples/l1`。

**无长期 dual-read：** 不再把「task 根 `bora.yaml` 按 task schema 解析」当作规范路径。

#### 成员（Task）一级布局约束（allowlist）

Task 成员目录 **一级目录只允许从已知集合取用**；除固定根文件外，不鼓励再出现自由命名的一级文件夹或根级业务模块。Config 校验可以对未知一级路径发出 warning 或 error。

**固定根文件（名字稳定）：**

| 文件 | 角色 |
| --- | --- |
| `README.md` | task 级说明（给人读；非 Runtime 输入） |
| `task.yaml` | 成员唯一配置入口（`bora.task/1`） |
| `harness.py` | `harness.entrypoint` 默认落点（路径可在 yaml 覆盖，但推荐固定） |
| `evaluator.py` | `evaluation.entrypoint` 默认落点 |

根级 `.py` 尽量只保留 entrypoint。支撑逻辑进入 `lib/`（或经 `upstream/` 复用），不要在 package 根上继续堆 `diagnostics.py`、`utils.py` 这类自由命名模块。

**允许的一级目录：**

| 目录 | 角色 | 主要消费者 | 是否 Attempt 热路径 |
| --- | --- | --- | --- |
| `prompts/` | 角色自然语言；进入模型的文案权威 | Harness 组装 messages | 是 |
| `schemas/` | 结构化输出契约 | Harness / Agent structured output | 是 |
| `environment/` | Environment / Provider 资产：SQL seed、fixture、**L1 `Dockerfile`** 等 | `environment.setup_steps` 的 `input_ref`；`provider.kind: docker` 时的 Attempt 镜像构建 | 是（setup / L1 prepare） |
| `evaluation/` | Evaluator-only 输入（gold labels、task contract） | `evaluation.inputs` 的 `package_path` | 是（评测阶段） |
| `data/` | Agent 可见任务数据（可选） | workspace mount / Harness 读取 | 视 task |
| `lib/` | **package-local Python 支撑**（task 作者编写、仅本 package 使用） | `harness.py` / `evaluator.py` import | 是 |
| `upstream/` | 上游 Benchmark 原样或薄适配代码（语义 owner 仍在上游） | harness bridge 调用 | 视 conversion |
| `solution/` | conversion 正负例、replay、验收夹具 | 人 / conversion CI；**不是** Attempt 默认依赖 | 否 |

按 **Core 可见性 / 契约角色** 分层，而不是按「是不是 Python」分层。同一语言的文件可以分别落在 `lib/`、`upstream/`、`solution/`，因为它们的读者和生命周期不同。

**三种资产目录（便于扫读）：**

| 类 | 目录 | 谁消费 |
| --- | --- | --- |
| Agent 输入文案与契约 | `prompts/`、`schemas/`、可选 `data/` | Harness / Agent |
| 环境与 evaluator-only 输入 | `environment/`、`evaluation/` | Runtime setup / Evaluator |
| 人与 conversion | `README.md`、`solution/` | 人、conversion 流水线 |

#### `lib/` 与 `upstream/`（不要与 Harness Core helper 混淆）

设计文档里的 **Harness Core helper**（`Agent`、`ToolSet`、`CallLimit`、`bounded_gather` 等）是跨 task 的可选 SDK，**不**拷贝进 Task Package，也 **不**用 package 一级目录 `helpers/` 表示——该名字与 SDK 术语冲突，禁止作为一级目录。

| 位置 | 放什么 | 不放什么 |
| --- | --- | --- |
| `lib/` | task 作者编写的支撑模块：tool body（如 `action_id → SQL`）、message 组装、workflow 子步骤、窄 bridge | Harness Core SDK；上游大段原样代码 |
| `upstream/` | 从原 Benchmark vendoring / 薄适配、语义仍按上游理解的代码 | task 新写的业务表、BORA 专用 glue（应进 `lib/`） |

`upstream/` 准入（与 [08 转换](08-conversion-security-testing.md) 一致，可更严）：

1. 语义 owner 仍是原 Benchmark；
2. 主要是复用或薄适配，不是重写业务；
3. 能回答：「去掉 BORA 包装后，这段是否仍像 upstream 模块？」

未满足条件的逻辑留在 `lib/` 或 harness 入口文件。没有真·上游 vendoring 的 task **不要**硬造空的 `upstream/`。

`lib/` 内部可用二级目录（如 `lib/tools/diagnostics.py`），但 **不要** 为每个模块再开一级 package 目录（禁止并列出现 `diagnostics/`、`tools/`、`utils/`、`helpers/` 作为一级）。

#### Dataset 级 `shared/`（#65）

同构多 task Dataset 可在 **Database 根** 放可选 `shared/`，避免把同一 bridge / 领域资产复制进每个 `tasks/<id>/lib/`。这是 BORA 显式增强，**不是** Harbor 布局 parity。

**规范子树（v1）：**

| 路径 | 角色 | 默认可见性 |
| --- | --- | --- |
| `shared/lib/` | 跨 task Python 支撑（import only） | 经 Database 根 on path 以 **`shared.lib.*`** 导入；**不**默认投影到 Agent workspace |
| `shared/assets/` | 只读领域数据（db / policy / fixtures） | Harness/Evaluator 用 **代码路径** 读取；v1 **无** `task.yaml` 资产声明面 |
| `shared/README.md` | 给人读的共享区说明 | 非 Runtime 输入 |

**Import 注入契约（权威）：**

```text
sys.path 前缀（Harness worker 与 L0 evaluator 一致）:
  [task_dir, database_root, ...]
# 禁止把 shared/lib 或 tasks/<id>/lib 作为 path root 注入
```

| 作者写法 | 含义 |
| --- | --- |
| `from shared.lib.xxx import …` | Dataset 级 glue（`shared/lib/`） |
| `from lib.yyy import …` | 仅本 task 的 `tasks/<id>/lib/` |

`shared/` 与 `shared/lib/` 须为可 import 包（推荐带 `__init__.py`；namespace package 为后置可选）。task 侧 `lib/` 同理（需要 `from lib…` 时）。

**硬规则：**

1. **Digest / publish：** 若 `shared/` 存在，其下文件 **必须** 进入 `member_paths_for_digest` 与 publish blob（与 `tasks/**` 同算法过滤 `__pycache__` / 多数隐藏文件）。改 `shared/` ⇒ 改整包 `packageDigest`。无 `shared/` 的包行为与今日一致。
2. **Import：** L0 worker 注入 **`task_dir` + `database_root`**（顺序见上表）；**禁止** 再把 `shared/lib` leaf 插入 path。Harness 与 Evaluator 均可 `from shared.lib…` / `from lib…`。**禁止**依赖 host 绝对路径。
3. **Agent 可见性：** 默认 **不** mount / 不投影 `shared/` 到 Agent workspace。可选 `shared/assets` Agent mount 为后续能力，不在 v1 默认路径。
4. **禁区：** `shared/` 下 **禁止** evaluation gold、host secrets（如 `.env`）、Docker socket 绑定物等。Gold **只** 在成员 `evaluation/`。
5. **顶层名 `shared` 保留（硬失败）：** 成员 task **禁止** 拥有 `tasks/<id>/shared/` 目录或 `tasks/<id>/shared.py`（与 Dataset 包名 `shared` 在 path 上同级时会 shadow）。Config/lock 校验 fail closed；检测脚本作验收门槛。**不再** 因 `shared/lib` 与 `tasks/*/lib` 同名 stem（如双方都有 `bridge.py`）而 ban——命名空间已区分 `shared.lib.bridge` vs `lib.bridge`。
6. **L1 / 镜像：** Core **禁止** 隐式把 `shared/` COPY 进 Attempt 镜像或默认塞进 build context。若容器内需要 `shared/` 内容，由 **task 级** `environment/` Dockerfile（或包内镜像配方）**显式** `COPY shared/`，并使 **Database 根**（或等价布局）进入容器 `PYTHONPATH`，以便 `shared.lib.*` 可 import。无静默 Core copy。L0 inject **≠** L1 自动可用。
7. **无 shared sub-digest：** Registry 不维护单独的 shared digest；整包 `packageDigest` 已覆盖 `shared/**`。
8. **证据等级：** 存在 `shared/`、digest 包含 `shared/**`、或 Hub Shared UI **不**抬高证据等级；仍按公开 smoke / Issue 验收声明 `runnable-mvp` / `isolated` 等。本 import 契约变更 **不** 抬高证据等级。

**`shared/lib` vs task `lib/`：**

| 放哪里 | 何时 | Import |
| --- | --- | --- |
| `shared/lib/` | 多 task 共用的 bridge、领域工具、稳定 glue | `from shared.lib…` |
| `tasks/<id>/lib/` | 仅该 task 的扩展；**允许** 与 shared 同 stem 文件名 | `from lib…` |

**资产引用：** v1 仅代码路径（例如相对 Database 根的 `shared/assets/...`，或 Runtime 注入的 database root + 相对路径）。不增加 `task.yaml` 声明语法。

**迁移（从 leaf inject）：** 旧写法 `from bridge import …`（依赖 `shared/lib` 在 path 上）改为 `from shared.lib.bridge import …`；生成器与包内 thin harness/evaluator 同步。

#### 文本分层：README、prompts 与 runtime payload

Package 里的自然语言按读者与用途分层，**不**强制存在根级 `instruction.md`（或任何等价的「全局任务说明书」文件）：

| 内容 | 推荐位置 | 是否 Runtime / agent 输入 |
| --- | --- | --- |
| Task 背景、目标、给人读的约束摘要、package 导读 | task 级 `README.md` | 否。仅文档；Campaign UI 若需要摘要可单独投影，不经由 `bora.yaml` 挂文件 |
| 角色规则、system 文案、角色专属约束 | `prompts/`（按角色分文件） | 是。由 `harness.py` 读取并组装 messages |
| 结构化输出契约 | `schemas/` | 是（schema），不是自然语言 prompt |
| 当轮 observation、findings、branch 数据 | `harness.py`（或 `lib/`）拼进 user message | 是 |

约定：

1. **Task 说明写 README，不写强制输入文件。** 背景、固定假设集合、评测意图这类「给人理解这题在干什么」的文字放在 package 的 `README.md`。Core 不要求 `harness.instruction` 或根级 `instruction.md`。
2. **提示词统一放 `prompts/`。** 进入模型的角色文案只维护在这里，避免 README、根级 instruction 与 system prompt 三处重复。Harness 可以做占位符替换，但不应再依赖第二套全局 instruction 文件。
3. **Harness 组装 messages 时区分「角色文案」与「运行时数据」。** system（或等价角色槽）来自 `prompts/`；user 侧以当轮数据为主（observation、findings、允许 label 列表等），而不是再粘贴一遍 task README。
4. **允许更简单的 task 形态。** 单 agent、无多角色协作的 task 可以只有一个 prompt 文件；没有角色提示需求时甚至可以没有 `prompts/`，由 harness 直接构造 messages。需要自然语言约束时，仍优先落在 `prompts/`，而不是发明新的根级约定文件名。
5. **一级目录只从 allowlist 取用。** 新增 package 资产时先归入上表角色；只有角色本身成为 Core 契约后，才扩展 allowlist，而不是为单个 task 发明一级目录名。
6. **Evaluator-only 输入统一用 `evaluation/`。** 该目录不挂载给 Harness/Agent；不再使用 `verifier/` 作为一级目录名（避免与「clean verifier 进程」口语混淆）。

### `bora.yaml` 的顶层结构

> 历史标题保留锚点。**成员执行契约文件名是 `task.yaml`**（`format: bora.task/1`）。Database 根仍用 `bora.yaml`（`bora.database/1`），仅 identity/version/tasks 根，不含下列执行区。

成员 `task.yaml` 推荐分成七个明确区域：

| 配置区域 | 内容 | 主要消费者 |
| --- | --- | --- |
| `harness` | runtime、entrypoint（定位 package-local 入口；不含任务说明文件） | Config Core、Provider |
| `parameters` | 模型引用（role id）、轮数、Tool 上限、context strategy | Harness |
| `provider` | container、platform、workspace、network、secret projection | Runtime、Provider |
| `agent_profiles` | **角色槽**（role id + 可选 workspace 约束）；**不含** executor/entry/model | Config Core 合并后 → **Agent Service** |
| `environment` | 外部资源、lifecycle、action allowlist | Runtime、Environment Manager |
| `limits` | wall time、memory、process、Agent/Environment 外层硬上限（**任务契约**，job 不可覆盖） | Runtime、Provider、Capability |
| `artifacts` / `evaluation` | 可发布产物、Evaluator 输入、隔离和结果格式 | Artifact Owner、Evaluator Runner |

`parameters` 是统一的实验参数空间。`harness` 只定位入口（`runtime` + `entrypoint`），不再同时保存另一套 `params`，也不挂载任务说明或 prompt 路径。这样可以避免 `harness.params`、`tool_limits` 和 Campaign override 分散在多个位置；自然语言提示词由 package 的 `prompts/` 与 `harness.py` 负责。

### Task 身份 vs Job binding（#59）

| 轴 | 归属 | Leaderboard |
| --- | --- | --- |
| harness / evaluator / gold / intent `limits` / 角色槽拓扑 | **Task / package 身份** | 改了 ≈ 新 task 或新 version |
| agent entry + model（`profiles.yaml` / CLI overlay） | **Job binding** | 新 `config_fingerprint` |
| host secrets（`.env` 值） | 本机 only | 不进 fingerprint / lock / upload |
| suite concurrency / Always-k `n_attempts`（及 pass@k job 指标） | CLI / job 调度；**禁止**写进 `task.yaml` | **不是**排行榜身份键（metrics 另列；Hub 可选展示 pass@k / pass^k / n_attempts，#60） |

**Merge 顺序（Config Core 唯一读者）：**

```text
member task.yaml（角色槽 + intent + harness/eval）
  ⊕ Database profiles.yaml（默认 job binding）
  ⊕ CLI `--profiles`（可选，整文件替换 Database 默认）
  ⊕ CLI `--set` `/bindings/<role>/…` 与 `/parameters/*`
  → load_and_lock → LockedTaskConfig（resolved agent_profiles + job_overlay）
  → actors_summary → config_fingerprint
```

- 成员 `task.yaml` **禁止**内联 `executor` / `model` / `options` / `api_key` / `base_url` / `label`（无向后兼容双写法）。
- Job binding 可选 `label`：Jobs / Hub 的 Agents 轴。缺省：`executor: acp` 用 `options.entry`，其它 kind 用 `executor`。**禁止**用 `options.agent` 当展示名。写入 lock `job_overlay` 与 Attempt/suite `agent_label`。
- 缺 required role binding → `missing_binding` fail closed。
- Intent `limits.*` **不可**经 `--set` 覆盖。
- Leaderboard **job 轴**是 suite 级 `profiles.yaml` / `job_overlay`（role id → entry/model），不是「各 task 角色槽拓扑是否相同」。不同 task 可用不同 role id；只要绑定文档一致，`config_homogeneous` 仍为 true，公开可比榜展示该 yaml。
- 仅当同一 suite 内出现**同一 role id 的 entry/model 冲突**（或无法解析 job 轴）时 `config_homogeneous: false`。

**Agent 后端可切换、可混用**是一等需求（见 [05-runtime/agent-service.md](05-runtime/agent-service.md)）：`parameters.models.*` 只点 **role / profile id**；真正跑哪条 coding-agent 后端写在 Database `profiles.yaml`（或 CLI overlay）。coding-agent 配置形状为 `executor: acp` + `- plugin: acp` 行上的 `options.entry`（registry entry_id：`codex` / `claude-code` / **`pi`** / `opencode` / `grok-build`…）；`openai-http` 为独立 api-client。Campaign 换后端时优先改 binding 的 executor 行 `options.entry`/`model`（`--set '/bindings/solver/…'` 或 `--matrix`），不必改 `harness.py`。

#### L1 / `provider.kind: docker` 与 package Dockerfile

当 `provider.kind` 为 **`docker`**（L1 Attempt）时：

1. **Package 必须提供 Dockerfile**，默认路径 **`environment/Dockerfile`**（相对 package 根）。可用 `provider.dockerfile` 覆盖为 package 内相对路径（仍须落在 package 内）。
2. Dockerfile **不在 package 根**作为一级自由文件名推广；与 Environment / Provider 资产同属 `environment/`。
3. 两种合法形态（均由 package Dockerfile 表达，不由 Core 代写）：
   - **官方基座**：`FROM bora-attempt:l1`（仓库 `docker/attempt` 构建一次、多 package 复用）。设计契约：预装最低 ACP 验收 entry 的 **engine + ACP 入口**（Mode 1：`codex`+`codex-acp`、`claude`+`claude-agent-acp`、**`pi`+`pi-acp`**；Mode 2：`opencode acp`；Mode 3：exact Grok pin）。build 期 bake-in，禁止 invoke 时 `npm i` / floating `npx`。
   - **上游基座**：`FROM <upstream>` 再按 **同一 pin lock** 安装所需 entry（禁止 floating `latest` / invoke 时 `npx`）。
4. `load_and_lock`：docker 且 Dockerfile 缺失 → fail closed（`missing_reference`）。
5. 镜像 **构建与 digest** 在 Attempt prepare 时发生；secret **不得** bake 进镜像层（credential 仅 run 时投影）。

##### L1 多 Actor `agent_isolation`

Docker L1 package 可在 `provider.agent_isolation` 声明逻辑 actor 拓扑。YAML 不声明 container id、UID/GID、Docker network name、IPC path、credential 或 live handle；这些物理绑定由 Provider 在 Attempt prepare 时生成。

```yaml
provider:
  kind: docker
  assurance: l1
  network: bridge  # v1: bridge | none；所有 Agent target 共用 Attempt 级策略
  agent_isolation:
    mode: container-per-group  # shared-container | container-per-group
    groups:
      - id: analysis
        actors:
          - id: planner
            profiles: [planner-pi]
          - id: reviewer
            profiles: [reviewer-codex]
        shared_write: [workspace/team]
      - id: worker-a
        actors:
          - id: worker-a
            profiles: [worker-codex]
```

`load_and_lock` 必须 fail closed 校验：

- `mode` 只能是 `shared-container` 或 `container-per-group`；group 非空、group id 唯一、actor id 全局唯一，且每个 actor 恰好属于一个 group；
- 每个 `profiles[]` 条目必须引用已有 `agent_profiles[].id`；L1 open 缺少 `actor_id`，或 `(actor_id, profile_id)` 不在 allowlist 时拒绝且不执行 container exec；
- `shared_write` 默认空；每条路径必须是 workspace-relative，不得为绝对路径、包含 `..` 或经 symlink 逃逸，并且必须落在该 group 全部参与 actor 已锁定 write view 的交集内；
- `provider.network` v1 只能是 `bridge` 或 `none`，适用于本 Attempt 的全部 Agent target；不接受 group/actor 级 network 声明；
- `shared-container` 所选 executor 若不能以 non-root numeric UID 运行，lock 或 prepare 返回 `unsupported_capability`，禁止提权或回退 host；
- YAML 中出现 container id、numeric UID/GID、socket path、Docker network runtime name、credential value 或 live handle 时拒绝。

### MVP 配置示例

下面使用文档内的 `database-52-mvp/` 概念 package 说明默认路径。它与 `database-52/` 表示同一个 benchmark task，但只保留当前诊断实际需要的 PostgreSQL、L1 path views、Attempt 硬顶和完整 evaluator contract；下方 YAML 即本设计的完整规范示例。

```yaml
format: bora.task/1
task_id: database-52

harness:
  runtime: python
  entrypoint: harness:run

parameters:
  models:
    specialist: codex-database-specialist
    planner: codex-database-planner
    reducer: codex-database-reducer

  workflow:
    specialist_concurrency: 5
    max_follow_up_assignments: 1

  agents:
    specialist:
      max_turns: 1
    planner:
      max_turns: 1
    reducer:
      max_turns: 1

  tools:
    defaults:
      max_calls: 2

provider:
  kind: docker
  platform: linux/arm64
  network: agent-provider-only
  assurance: l1
  # dockerfile: environment/Dockerfile  # 默认；package 内必填（见上文 L1 / provider.kind: docker）
  workspace:
    views:
      harness:
        read: [/task/harness.py, /task/lib, /task/prompts, /task/schemas]
        write: [/workspace]
      agents:
        read: [/task/prompts, /task/schemas]
        write: [/workspace/work]

agent_profiles:
  # profile = 可切换的 Agent 后端绑定；见 design/05-runtime/agent-service.md
  # 成员只声明角色槽。coding-agent 绑定见 Database profiles.yaml：
  # executor: acp + - plugin: acp / options.entry
  - id: codex-database-specialist
    workspace_view: agents
  - id: codex-database-planner
    workspace_view: agents
  - id: codex-database-reducer
    workspace_view: agents

environment:
  id: database-attempt
  kind: multi-service
  lifecycle: attempt-local
  components:
    - component_id: postgres
      image: docker.io/library/postgres@sha256:ac74e8c63c516b1f81fbaaede0663981399f80e42369431136b2455557f8547b
      platform: linux/arm64
      network_alias: postgres
  setup_steps:
    - step_id: initialize-schema
      component_id: postgres
      input_ref: environment/init.sql
    - step_id: create-anomalies
      component_id: postgres
      input_ref: environment/anomalies.sql
  action_commands:
    - command_id: postgres-readonly-diagnostic
      component_id: postgres
      action_ids:
        - inspect_insert_workload
        - inspect_lock_contention
        - inspect_vacuum
        - inspect_redundant_indexes
        - inspect_fetch_workload
  teardown_order:
    - postgres

limits:
  wall_time_seconds: 900
  memory_mb: 1024
  agent_invocations: 8
  environment_actions: 20

artifacts:
  publishable:
    - id: reducer-output
      producer: harness
      path: artifacts/reducer-output.json
      media_type: application/json

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: reducer-output
      target: artifacts/reducer-output.json
    - package_path: evaluation/task.json
      target: task.json
  output:
    format: json
```

这里沿用 `multi-service` Adapter contract，但只有一个 PostgreSQL component；该 kind 表示可组合能力，不要求 sidecar 齐套。这份配置没有 `actors`、`branch_plans`、`branch_execution` 或 `collaboration`。五个 specialist 的业务身份、Planner 的 follow-up 算法和 Reducer 的输入组合都写在 `harness.py`；只读诊断 SQL 等支撑逻辑在 `lib/`。`evaluation/` 没有挂载给 Harness 或 Agent，gold 只在 writer 停止后由 Runtime materialize。Tool 软限仍集中在配置中，由 Harness 的 `CallLimit` 使用。`parameters.models.*` 只引用 profile id；整 task 换 Claude Code / Pi entry，或「specialist=Codex entry、planner=Pi entry」时改 `agent_profiles` 的 `options.entry` / 引用即可，不必改 workflow 代码。

### 哪些值必须进入配置

满足任一条件的值进入 `bora.yaml`：

- 需要在不同 Trial 中比较；
- 需要由 Campaign variant 覆盖；
- 需要影响运行身份或结果解释；
- 需要由宿主机提前准备资源；
- 需要在运行前校验引用或 capability；
- 需要由 evaluator 或结果聚合读取。

典型例子包括模型 profile、temperature、seed、Agent turn、Tool 上限、retry、context strategy、并发、Provider image、resource、network、workspace、Artifact 和 evaluator input。

只描述实现结构且不会参与实验的常量可以留在代码中，例如 `DATABASE_TOOL_IDS`、prompt 模板函数和一个 task-local result mapper。它们如果开始参与实验，就提升到 `parameters`。

### 禁止的配置来源

下面这些写法会破坏统一管理：

```python
MAX_TOOL_CALLS = 2
MAX_REVIEW_ROUNDS = 3

max_calls = int(os.getenv("MAX_TOOL_CALLS", "2"))

tool_limits = yaml.safe_load(
    Path("tool-limits.yaml").read_text()
)
```

允许使用环境变量的范围很窄：credential locator、runtime placement 和部署差异。环境变量不能保存隐藏的实验语义。

## Core 1 详细设计：Config

### 职责

Config Core 是 task 配置的唯一读取与锁定模块，对外负责：

1. 读取 `bora.yaml`；
2. 合并明确的默认值、Campaign variant 和 CLI override；
3. 校验引用、能力与路径；
4. canonicalize 并生成 digest；
5. 返回一份不可变 `LockedTaskConfig`，使 Trial 可比较、可复盘。

Config Core 不 import `harness.py`，不执行 evaluator，也不根据 Python AST 推导 workflow。

### 内部模块

公共 facade 可以由 `model.py` 与 `load_and_lock.py` 实现。读取、merge、validation、canonicalization 和 digest 可继续拆成内部函数或文件，但文档不要求五段流水线、五个中间对象或固定目录数量。

```text
bora.yaml + variant + explicit overrides + capability catalog
  → load_and_lock()
  → LockedTaskConfig
```

### 配置对象

```python
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LockedTaskConfig:
    task_id: str
    harness: "HarnessConfig"
    parameters: "ParameterTree"
    provider: "ProviderConfig"
    agent_profiles: tuple["AgentProfileConfig", ...]
    environment: "EnvironmentConfig | None"
    limits: "RuntimeLimits"
    artifacts: "ArtifactConfig"
    evaluation: "EvaluationConfig"
    resolution: "ResolutionRecord"
```

`LockedTaskConfig` 是 Trial 的唯一配置真相。锁定之后对消费者做**轻量投影**，而不是再复制多份可持久化 Config DTO：

- Runtime / Provider 读取 envelope 相关 sections（provider、environment、limits、artifacts、evaluation）；
- Harness 只经 `ctx.params`（`HarnessParameterView`）读取 `parameters`——这是 parameter **view/projection**，实现成本低、接口清晰；
- gold 与 hidden material **不**靠「配置里删字段」隔离，而靠 workspace **不 mount** + 评测前 materialize，以及 credential/network projection。

Provider credential 由 Runtime credential store 注入。不必为每个消费者维护 Loaded→Resolved→Projected 类型阶梯。

### Config Core façade

```python
class ConfigCore:
    def load_and_lock(
        self,
        package_root: Path,
        task_id: str,
        *,
        variant: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        capabilities: CapabilityCatalog,
    ) -> LockedTaskConfig:
        ...
```

这是一个进程内领域函数，不需要独立 Config Service。内部 resolve/validate 仍然 fail closed；只有多个控制面需要共享、并发修改或 reopen 配置时，才有理由引入 durable store。

### 覆盖顺序

覆盖顺序固定为：

```text
bora.yaml
  → Campaign variant
  → CLI explicit override
  → resolved config
  → LockedTaskConfig
```

所有覆盖都必须：

- 指向允许覆盖的字段；
- 通过相同校验；
- 出现在 `ResolutionRecord`；
- 在 Attempt 启动前完成；
- 进入 Trial identity 和结果摘要。

运行中不允许热更新 Tool 上限、模型 profile、workspace grant 或 evaluator input。

### 配置校验

Config Core 至少检查：

- `format` 和 `task_id`；
- Harness entrypoint locator；
- `parameters` 是 JSON/YAML-compatible value；
- model profile 引用存在；
- Provider 与 platform 可用；
- workspace path 位于声明 root；
- Environment kind 和 lifecycle 受支持；
- `action_commands` 只引用已有 component；
- limits 为非负且在实现支持范围内；
- Artifact producer、path 和 evaluator input 引用一致；
- evaluator runtime、network 和 output format 有对应实现。

Config Core 不校验某个 Planner 会选择哪个 specialist，也不检查 Harness 是否真的调用某个 Tool。前者属于运行时算法，后者由 Harness 和测试确认。

### Package provenance（溯源，可选）

复刻 / 移植类 package 应声明 **provenance**，回答「复刻自哪、钉在哪一版」，便于对照 upstream 做流程保真检查。Provenance **不是** Attempt PASS，也**不是** package 质量分（质量审计见后续 issue，不与 evaluator verdict 混写）。

#### 写在哪

| 场景 | 位置 |
| --- | --- |
| 整包来自同一 suite | Database 根 `bora.yaml` |
| 个别 task 是复刻 | 成员 `task.yaml` |
| 两边都有 | **task 整段覆盖** database 默认（不做字段级 merge） |

#### 最小形态

```yaml
provenance:
  kind: port            # port | reimplementation | wrapper | original
  upstream:
    name: tau-bench
    url: https://github.com/example/tau-bench   # 复刻类必填
    ref: v0.1.0                                 # tag/branch；与 commit 至少填一个
    commit: abc123def456                        # 建议钉死
    task_id: airline-001                        # 上游若有 id
    paper: https://arxiv.org/abs/...            # 可选
  parity:
    claims: [protocol, scoring]                 # 声称对齐哪些面
    known_gaps: []                              # 已知刻意差异
```

#### 校验规则（fail closed）

- `kind: original`：可省略 `upstream`。
- `kind` 为 `port` / `reimplementation` / `wrapper`：必须有 `upstream.url`，且 `ref` 或 `commit` 至少一个。
- 未知键、错误类型 → `invalid_schema`。
- 字段**完全省略**时不强制（不挡 lock）；作者写了复刻类 `kind` 则按上表强制。

锁定后 provenance 进入 `LockedTaskConfig`（参与 digest），并出现在 `bora lock` 摘要与 Attempt evidence `lock.json`（若本 run 写了 lock summary）。**Attempt PASS 仍只来自独立 evaluator。**

## Database Registry 分发

**Release 单位 = Database 整包**（根 `bora.yaml` + 可选 `shared/**` + 全部 `tasks/**`）。Registry 是独立服务（`services/registry/`），不进入 Core 五组。

### PackageRef

| 形态 | 示例 |
| --- | --- |
| 本地 path | `./my-database` / `examples/core` |
| 版本坐标 | `example/core@0.1.0` |
| 内容钉死 | `example/core@sha256:<packageDigest>` |

本地目录存在时优先当 path；否则按 ref 解析。

### 双 digest

| Digest | 算法 |
| --- | --- |
| packageDigest | 排序相对路径 + 每文件 sha256 行 + 外层 sha256（`src/bora/registry/digest.py`） |
| blobDigest | 确定性 tar+gzip 字节的 sha256 |

Media type：`application/vnd.bora.database.v1.tar+gzip`。

### Cache

默认 `.bora/cache/databases/<database_id>/<packageDigest>/`（可用 `BORA_CACHE_ROOT` 改根）。仅 dual-digest 校验通过后 atomic rename；半拉目录不可见。

### CLI

```text
bora publish <database-path> [--public]   # 默认 private
bora lock|run <path|ref> --task <id>      # ref 经 verified cache 后走 Database resolve
```

配置：`BORA_REGISTRY_URL` + `~/.bora/credentials`（0600）。客户端永不持有 blob store credential。

## Suite 执行 vs Campaign

| | Suite run | Campaign | Always-k |
| --- | --- | --- | --- |
| 轴 | 同一 Database 的 **task_id** | 同一 task 的 **parameter matrix** | 每 task **k 次独立 Attempt** |
| CLI | `bora run <database> [--task] [--max-concurrent-tasks N] [-k N] [--resume-suite id]` | `bora campaign … --matrix` | 同上 `-k` / `--n-attempts`（**非** matrix） |
| PASS | **仅** per-task evaluator；无 suite PASS | 每 variant 独立 Trial PASS | 仍仅 per-Attempt evaluator；job 再算 pass@k |
| 失败 | 默认可 `bora cancel suite_…` 停新 unit | 既有 campaign 策略 | 补跑只追加 Attempt |

Summary 写在 Database 根：`.bora/suite-runs/<suite_run_id>/summary.json`（另有 `progress.json`；cancel 可写 `cancel.requested`）。

### Suite metrics（观测聚合，非 PASS 权威）

Suite summary 含 `metrics` 对象（`bora.suite.summary/1` 附加字段），供 job/dataset 级展示与 Registry suite-result 上传：

| 字段 | 公式 / 语义 |
| --- | --- |
| `pass_rate` | `count(status==PASS) / n_tasks`（一 task 多 Attempt 时，按实现的 task 行聚合规则） |
| `mean_score` | 各 task `score` 的算术平均；**缺 score / 非数值 / status=ERROR → 0.0**（Harbor 缺 reward 当 0） |
| `n_tasks` / `n_pass` / `n_fail` / `n_error` | 计数；未知 status 计入 `n_error` |
| `missing_score_as` | 固定 `0.0`（文档化默认） |
| `n_attempts` | 本次 job 的 Always-k 预算（CLI/job；**不进** fingerprint） |
| `k_values` | 本 summary 计算过的 k 列表 |
| `pass_at_k` | **pass@k**：无偏估计 \(1 - C(n-c,k)/C(n,k)\)（Harbor / Chen）；suite 分 = **对 task 取 mean**；`n < k` 的 task 不进该 k 分母 |
| `pass_power_k` | **pass^k**：\((c/n)^k\)（k 次都成功）；同样对 task 取 mean |
| `per_task` | 各 task 的 `n` / `c` 与 per-k 映射（审计；非 identity） |

**`pass_at_k` / `pass_power_k` 值形状**（k 键为字符串）：

```text
{ "<k>": { "value": float|null, "n_tasks": int, "incomplete_tasks": int }, ... }
```

**禁止** suite-level PASS 字段作为最终权威；PASS 仅 per-task evaluator。`exit_code` 与 `counts` 仍是操作者退出/计数语义，不是榜单 PASS。  
pass@k / pass^k **不是** package 身份 / `config_fingerprint` 键；不同 k 的 job 可并列展示，身份仍是 agent×model 绑定。

### Suite/job 结果上传（Registry）

本地 suite 跑完后可将 `.bora/suite-runs/<suite_run_id>/` 上传为 **suite result 行**（meta + 可选 archive），供 Leaderboard 查询。公开榜只收**完备且绑定 release** 的 suite（见 [12](12-hub-dataset-and-leaderboard.md)）：

| CLI | 语义 |
| --- | --- |
| `bora results upload-suite <db> --suite-run <id>` | 上传聚合分 + `task_refs` + summary 归档；上传前本地 **ensure/recompute** k 指标 |
| `bora results get-suite <id>` / `list-suites` | Registry 查询（`metrics` 原样返回，**不剥除** pass@k） |
| `… --local <db>` | 不启 Registry，回落本机 `.bora/suite-runs/` |

API：`POST/GET /v1/results/suites`（可见性与 attempt 一致：public / `results:read`）。  
`GET …/suites?board=1` 只返回完备且 `bound_kind=release` 的行；Jobs 列表不加该过滤。  
响应含 `pass_rate`、`mean_score`、`metrics`（含 `pass_at_k` / `pass_power_k` 若有）、`task_refs`（可含 `n`/`c`/`attempt_run_ids`）、`complete` / `bound_kind`；**不**接受/存储 suite PASS。  
一等列仍是 `pass_rate` / `mean_score`；k 指标读 `metrics` 即可（无需额外 first-class 列也可展示）。

