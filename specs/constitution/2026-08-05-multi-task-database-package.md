# 实现决策：多 Task Database 包（布局 · 分发 · suite 执行）

## Metadata

| Field | Value |
| --- | --- |
| Decision date | 2026-08-05 |
| Owner | User（2026-08-05 对齐会话：#1–#6 已确认；实现仍待显式授权） |
| Status | **active — product decisions accepted**（实现未授权前不改 `src/`） |
| Scope | 分发与批量执行单位从「单 task 目录」升级为 **Database（suite）**；根配置 vs 成员配置边界；registry 整包分发；suite 并发与单 task 选择 |
| Related epic | [GitHub Issue #9](https://github.com/ffy6511/BORA/issues/9) |
| Related issues | [#10 format](https://github.com/ffy6511/BORA/issues/10) · [#11 registry](https://github.com/ffy6511/BORA/issues/11) · [#12 suite run](https://github.com/ffy6511/BORA/issues/12) · [#7 duplicate→#11](https://github.com/ffy6511/BORA/issues/7) |
| Related specs | [Spec 20](../active/20-database-suite-format-plan.md) · [Spec 21](../active/21-database-registry-plan.md) · [Spec 22](../active/22-database-suite-run-plan.md) |
| Design sync required | 实施前先改 [`docs/design/02-task-package-and-config.md`](../../docs/design/02-task-package-and-config.md)（及 glossary / overview 中「交付单元」表述）；Architecture 增加 registry / suite-run application 边界 |

## Decision Summary

BORA v2 的**规范交付与分发单位**是 **Database（suite）**，不是散落的单 task 目录。

| 层级 | 配置文件 | 位置 | 职责 |
| --- | --- | --- | --- |
| Database | **`bora.yaml`** | **仅** Database 根目录 | suite identity / version / 成员定位 / 可选默认与分发元数据 |
| Task | **`task.yaml`** | `tasks/<task_id>/` | 单题 harness / evaluator / provider / limits / profiles…（承接今日 task 语义） |

二者 **schema 不同**（`format` 字段区分），禁止混用同一文档模型。  
Registry **v1 只发布 Database 整包**（根配置 + 全部成员）。  
Suite 执行在 **Application/CLI** 层调度多个独立 Trial；**PASS 仍 per-task evaluator**，不存在 suite 级 PASS 权威。

实现顺序固定为：

```text
#10 / Spec 20  布局 + 本地 resolve
  ├─► #11 / Spec 21  registry 整包 publish/resolve（可选后置 e2e）
  └─► #12 / Spec 22  suite 并发 + 单 task（本地 Database 即可验收）
```

本 epic **不**直接勾选 Roadmap Version Index；版本验收在用户审查通过并完成实现后另开或并入后续 Roadmap 条目。

## Background

### Current system

- 每个 example 是「单 task 包」：根目录 `bora.yaml`（`format: bora.task/1`）+ harness/evaluator。
- `bora lock|run <package-dir> --task <task_id>` 要求 `--task` 与根 `task_id` 一致。
- 无 suite 成员表、无 Database identity、无 registry ref、无「一次命令跑多个 task」。
- Campaign（`bora campaign`）是**同一 task 的 parameter matrix**，不是跨 task 的 suite 轴。

### Problem

团队/社区需要：

1. 把多题集合作为**一个**可理解、可锁定、可分发的单位；
2. 用稳定 identity + version（+ content digest）publish / pull / 复现；
3. 在本地或 cache 上 **并发跑 suite** 或 **只跑其中一个 task**。

若继续把「单 task 根 `bora.yaml`」当作唯一交付形态，则 multi-task 只能靠 monorepo 人工拼盘，且 registry（Issue #7 方向）缺少清晰 release 对象。

### Product mapping (Harbor / bora-v0)

| | Harbor | bora-v0 | 本决策 |
| --- | --- | --- | --- |
| 集合配置 | `dataset.toml` | `benchmark.yaml` | **`bora.yaml`（Database）** |
| 成员配置 | `task.toml` | `tasks/*/task.yaml` | **`tasks/*/task.yaml`** |
| 分发 | task 与 dataset 可分 | 整包 archive | **v1 = Database 整包** |
| 栈 | Supabase 耦合 | 独立 registry + S3 + 双 digest | **UX 学 Harbor；信任边界学 v0** |

## User Narrative

操作者拿到（或 clone）一个 Database 目录：

```text
my-database/
├── bora.yaml                 # Database：identity / version / tasks 根
├── tasks/
│   ├── task-a/
│   │   ├── task.yaml
│   │   ├── harness.py
│   │   └── evaluator.py
│   └── task-b/
│       ├── task.yaml
│       └── …
└── README.md
```

1. **列举 / 锁定单题：**  
   `bora lock ./my-database --task task-a` → resolve 到 `tasks/task-a` → 读 `task.yaml` → 现有 `LockedTaskConfig` 语义（另记录 Database identity + suite digest 输入面）。
2. **单题运行：**  
   `bora run ./my-database --task task-a` → 独立 Attempt / Result / evidence；PASS 仅来自该 task 的 evaluator。
3. **整 suite（Spec 22）：**  
   `bora run ./my-database --max-concurrent-tasks 2` → 每个成员独立 lock/run；汇总 per-task 结果，**不**合成 suite PASS。
4. **分发（Spec 21）：**  
   `bora publish ./my-database` → 不可变 release；他机 `bora run <identity>@<version> --task task-a` 经 verified cache 后走同一本地 resolve。

## Final Decision

### D1. 交付单元与文件边界

1. **规范交付单位 = Database。** Task 是 Database 的成员，不是独立的 registry release 单位（v1）。
2. **根 `bora.yaml` 只允许 Database schema**（`format: bora.database/1`）。  
   **成员配置必须是 `task.yaml`**（`format: bora.task/1`），位于 `tasks/<task_id>/`（`tasks` 根可由 manifest 声明，默认 `tasks`）。
3. 目录名 **必须** 等于 `task.yaml` 内 `task_id`；否则 fail closed。
4. Database identity **只服务** publish / resolve / cache key / evidence 溯源，**不是** harness 业务参数，**不**参与 PASS。

### D2. Database `bora.yaml` 最小字段（字段名冻结）

```yaml
format: bora.database/1
database_id: example/demo-suite   # 见下方字符集；与 version 组成 release 坐标
version: "0.1.0"                  # 人类版本（字符串；非强制 semver 解析，但 publish 冲突按字面相等）
tasks:
  root: tasks                     # wire 路径；内部模型可映射为 tasks_root
# 可选：
# description: "…"
# defaults:                       # v1 白名单见下；禁止 task 执行契约键
#   max_concurrent_tasks: 1       # suite 调度默认；仅 Application 消费
```

规则：

- **`database_id` 字符集（v1 冻结）：**  
  - 匹配 `^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$`（单字符 id 允许单独 `[a-z0-9]`）；  
  - 长度 1–128；**大小写敏感**（规范写法全小写）；  
  - 禁止 `..`、连续 `//`、前导/尾随 `/`、空段；  
  - 推荐 `org/name` 或 `area/name` 风格。  
  非法 id → manifest load **fail closed**。
- `database_id` + `version` = 人类 release 坐标；**suite content digest**（算法 Spec 21）= 不可变钉死。
- **`defaults` v1 白名单（用户确认方案 A，2026-08-05）：**  
  - **仅** suite 调度键：`max_concurrent_tasks`（正整数 ≥1）；CLI `--max-concurrent-tasks` 覆盖。  
  - **禁止**根配置携带「所有 task 共享」的执行/硬顶/评测属性，避免与成员 `task.yaml` 歧义：  
    `limits`、`provider`、`harness`、`evaluation`、`agent_profiles`、`parameters`、`environment`、`artifacts` 等 **不得** 出现在 Database `bora.yaml`（含 `defaults` 内外）。  
  - 其它未知 `defaults` 键 → fail closed。  
  - Runtime 硬顶与执行契约 **只** 来自成员 `task.yaml` → `load_and_lock`。
- 根 `bora.yaml` **不得**声明 harness/evaluator/agent_profiles 等 task 执行契约。
- Wire `tasks.root` ↔ 内部字段 `tasks_root`：文档与 schema 以 wire 为准；代码可有映射层，禁止两套对外字段名并存。

### D3. Task `task.yaml` 语义

1. 承接今日根级 `bora.yaml`（`format: bora.task/1`）的全部执行与评测契约。
2. `load_and_lock` 的规范输入是 **task 目录 + task.yaml**（package root for harness/evaluator 解析 = 该成员目录）。
3. lock / Result / evidence 至少记录：`database_id`（若来自 Database）、`task_id`、task lock digest；有 suite digest 时一并记录；**永不**记录 store credential。

### D4. 迁移策略（禁止长期双权威）

**选定：一次性迁移到 Database 外壳，不保留「task 根也叫 `bora.yaml` 且按 task schema 解析」为规范路径。**

| 项 | 决定 |
| --- | --- |
| 仓内 examples / fixtures | Spec 20 **同批**改为 Database 布局（见下节 **Examples 验收布局**） |
| 单 task 包 | 作为某 Database 下的**一个成员**；不设第二套「单文件包」权威 |
| CLI 旧用法 | `bora run <dir> --task <id>` 的 `<dir>` 变为 **Database 根**；去掉对「task 根 bora.yaml」的读路径 |
| 过渡兼容层 | **不做**长期 dual-read；若实施期需要极短 shim，必须在 Spec 20 完成前删除，不得进 completed 状态 |

#### Examples 验收布局（用户确认，2026-08-05）

**规则：`examples/` 下每个一级子目录 = 一个 Database**（不是「每个今日 package 目录各自一个 Database」）。

| Database 根（path） | 建议 `database_id` | 成员来源（今日布局 → `tasks/<task_id>/`） |
| --- | --- | --- |
| `examples/core/` | `example/core` | 今日 `examples/core/*` 各子目录 → 成员（如 `config-minimal`、`sdk-agent-session`、`evaluator-negative`…） |
| `examples/journeys/` | `example/journeys` | 今日 `examples/journeys/*` → 成员（`env-postgres-min`、`multiagent-env-min`、`tau2-dialog-min`、`terminal-jsonl-agg`） |
| `examples/l1/` | `example/l1` | 今日 `examples/l1/*` → 成员（`sdk-session-single-actor`、`multi-agent-*`、`executor-image-*`…） |

目标形态示例（`journeys`）：

```text
examples/journeys/                    # Database 根
├── bora.yaml                         # format: bora.database/1；database_id: example/journeys
├── README.md                         # suite 级说明（可选）
└── tasks/
    ├── env-postgres-min/
    │   ├── task.yaml                 # 原 package 的 bora.yaml → task schema
    │   ├── harness.py
    │   ├── evaluator.py
    │   ├── environment/
    │   └── …
    ├── multiagent-env-min/
    ├── tau2-dialog-min/
    └── terminal-jsonl-agg/
```

验收命令形态（Spec 20 带 `--task`；Spec 22 可无 `--task` 跑全员）：

```text
bora lock examples/journeys --task terminal-jsonl-agg
bora run  examples/journeys --task env-postgres-min
bora run  examples/core     --task sdk-agent-session
bora run  examples/l1       --task sdk-session-single-actor
# Spec 22：
bora run  examples/journeys --max-concurrent-tasks 2
```

补充约定：

1. **`task_id` = 原目录名**（与今日 `task_id` 字段对齐；若 yaml 内 id 与目录名不一致，迁移时改到一致，fail closed）。  
2. 成员目录内资产（`environment/`、`evaluation/`、`data/`、`lib/`、`prompts/`…）**整棵迁入** `tasks/<task_id>/`，相对路径语义相对 **task 根** 不变。  
3. 原各 package 根 `README.md` 可迁入成员目录；Database 根可另有 suite 级 README。  
4. 测试/Skills/文档中所有 `examples/core/<pkg>` 路径改为 `examples/core --task <pkg>`（或 `examples/core/tasks/<pkg>` 仅作文件定位，**CLI 入口始终是 Database 根**）。  
5. 若 tests 需要最小夹具，可另建 `tests/fixtures/databases/…`；**公开 examples 验收以三个 Database 为准**，不另造与 `core`/`journeys`/`l1` 平行的第四套权威 examples 树。

### D5. CLI 入口形态（跨 Spec）

```text
bora lock  <database-path|ref> --task <task_id>
bora run   <database-path|ref> --task <task_id>          # 单 task（一等）
bora run   <database-path|ref> [--max-concurrent-tasks N]  # 全量 suite（Spec 22）
bora tasks <database-path|ref>                           # 列举成员（Spec 20 定名；可用 flag 替代）
bora publish <database-path> […]                         # Spec 21
```

- 本地 path 工作流 **零依赖 registry**。
- ref 语法（Spec 21 冻）：`<database_id>@<version>` 与 `@sha256:<packageDigest>`（digest 形式可带 identity 前缀，以 Spec 为准）。

### D6. Registry 分发（Issue #11 / 收束 #7）

1. **Release 单位 = Database 整包**（根 + 全部 `tasks/**`），不是单 task。
2. **产品 UX 学 Harbor**（publish / ref run / 默认 private）；**实现与安全学 bora-v0**：独立 Registry 服务、**HTTPS/HTTP JSON API**（不强制 gRPC）、双 digest、atomic verified cache、scoped API key。  
   - Harbor 默认连 **托管 Hub**；我们默认连 **可配置的自部署 Registry 基址**（开发本机 compose / 正式环境线上服务共用同一 API 契约）。
3. **推荐栈（v1 绑定）：**

| 层 | 选型 |
| --- | --- |
| Registry 服务 | 独立进程（`services/registry` 或仓外边界清晰路径）；**不**并入 Core 五组；**不是**每个 `bora run` 用户本机必起的守护进程 |
| 传输 | **HTTP(S) API only**（CLI ↔ Registry）；不要求 gRPC |
| Metadata | PostgreSQL（跑在 Registry 部署侧） |
| Blob | **S3 兼容 API**；**v1 本地/CI 默认实现 = RustFS**（bora-v0 已验证；compose 单一默认，不并列 MinIO 为双默认）。生产/其它环境可换任意 S3 兼容 endpoint（含自托管、R2）——仅 Registry 服务配置，**不**改 CLI 契约；**仅 Registry 服务持有 store credential** |
| CLI 凭证 | 主路径 `~/.bora/credentials`（0600）；CI 可用 env locator 注入同一逻辑凭证；禁止 argv/URL/lock/evidence |
| CLI 端点 | 可配置 **Registry base URL**（见 D6 配置键冻结）；开发 → 本机 compose；发版 → 线上自部署 HTTPS；**同一套 CLI 与 API** |
| Cache | 默认 `.bora/cache/databases/<database_id>/<packageDigest>/`（相对用户 cache 根，可经配置覆盖根目录；**布局结构固定**）；半拉缓存不发布 |

4. 客户端 **永不**获得 S3 endpoint/key/object key；只谈 Registry HTTP + 本地 cache 路径。  
5. Registry **不是** PASS / credential / Run identity authority。  
6. gold / evaluation 可在包内，但 **整包下载不改变** Provider 可见性规则（仍靠 mount + materialize）。  
7. 明确不选 v1：Harbor Supabase 强耦合、客户端直传 S3、只发 task + 远端清单、Registry 与 Runtime 共库、强制 gRPC。  
8. **Visibility 默认：`private`。** 仅显式 `--public`（或等价 flag）才创建 public release；private 未授权读 ≡ not found。  
9. **部署形态（用户确认，2026-08-05）：**  
   - 本地开发：端点指向本机（或 compose）上的 Registry + **RustFS**（S3 兼容）；  
   - 正式发版：端点改为线上自部署 Registry（blob 仍为 S3 兼容，具体厂商为部署配置）；  
   - 纯本地 path 工作流（不 publish / 不 pull）**零依赖** Registry。

10. **v1 工程默认（减少「xx 或 yy」；非第二产品语义）：**

| 项 | v1 唯一默认 | 备注 |
| --- | --- | --- |
| 本地 blob | **RustFS** | 不把 MinIO 写成并列默认；S3 适配器可接其它实现 |
| 元数据 DB | **PostgreSQL** | 无第二默认 |
| Registry 代码位置 | 仓内 **`services/registry/`**（可调包名但单路径） | 不并进 Core；不默认仓外黑盒 |
| Registry 语言 | **Python** | 对齐主仓；逻辑学 v0 |
| 传输 | **HTTP(S) JSON** | 不强制 gRPC |
| Archive | deterministic **tar + zstd**（media type 实施时写死一种） | 对齐 v0 方向 |
| Digest | **packageDigest（树）+ blobDigest（archive）** | 算法细节 Spec 21 Phase 0 钉死，不另选第二套 |
| 列举 tasks CLI | **`bora tasks <database>`** | 不用「子命令或 flag」双入口 |
| Examples `database_id` | **`example/core` / `example/journeys` / `example/l1`** | 去掉「建议」 |
| Suite summary 根 | **Database 根下** `.bora/suite-runs/<id>/summary.json` | 不用 cwd 相对 |
| base URL 配置 | env **`BORA_REGISTRY_URL`**（主）；credentials 文件可带默认 registry 段 | Phase 21 可补 flag 覆盖，不设第二套全局配置格式 |

仍属**部署可选、非产品二选一**（实现只保证 S3 API 契约）：生产 blob 落到自建盘 / R2 / 其它 S3——只改 Registry 服务配置。

### D7. Suite 执行（Issue #12）

1. 调度归属 **Application**（可复用 Campaign 并发原语思想），**不**把 task 目录扫进 Core，**不**由 Harness 解释 suite。
2. 每个 task：**独立** `resolve → load_and_lock →` 独立 Trial/Attempt/Result/evidence；禁止多 task 默认共享可写 workspace。
3. 并发：`--max-concurrent-tasks N`（N≥1）；Database `defaults.max_concurrent_tasks` 可提供默认，CLI 覆盖。
4. **单 task FAIL 默认不取消其余**（非 fail-fast）；任一 **ERROR** / 基础设施失败的 exit 策略在 Spec 22 写死。
5. **与 Campaign 正交：**  
   - Campaign = **同一 task** 的 parameter matrix；  
   - Suite run = **同一 Database** 的 **task_id 轴**。  
   二者可共用 worker 池实现，不可合并为一种配置语义。
6. **禁止** suite 级 evaluator 或单一 PASS 取代 per-task evaluator。

### D8. 权威与红线（跨 Spec 不变量）

- secret / API key / store credential **不进** yaml、lock、evidence、registry audit 正文。
- trajectory / `HarnessTerminal.completed` / suite 汇总 **≠** PASS。
- Control Plane 仍不 import task-local harness/evaluator 模块。
- Adapter 仍禁止按 Benchmark/task 名分支。
- mid-loop handoff（Issue #2）、job/trial 结果中心上传、**不在本决策范围**。

## Invariants

- Database 与 Task **双 schema、双文件名**；根 `bora.yaml` 永不为 task 执行契约。
- v1 registry release **只能是** Database 整包。
- PASS 权威 **仅** 独立 per-task evaluator。
- 本地 path 可完整开发与验收 suite run；registry 可选。
- Spec 20 完成后，仓内 **无**「task 根 `bora.yaml` 作为规范 task 配置」残留权威路径。

## Technical Boundaries

| 边界 | 归属 |
| --- | --- |
| DatabaseManifest 加载 / 成员 resolve / task.yaml lock | Config Core + Application resolve |
| Suite 并发调度、汇总 exit code | Application（非 Harness、非 Core Evaluation） |
| Registry HTTP、auth、blob、metadata | 独立 Registry 服务 + CLI/application client |
| verified cache 布局与双 digest 校验 | application resolve 路径（Core 只读已 materialize 的本地树） |
| Attempt 隔离 / hard ceiling / gold materialize | 现有 Provider / Runtime / Evaluation（不变） |

## Alternatives

| 方案 | 为何不选 |
| --- | --- |
| 保持单 task 包 + 外置「suite 清单」文件 | 双权威；清单与成员易漂移；与 Harbor 式 colocated 体验差 |
| 根与成员都叫 `bora.yaml` | 文件名碰撞、schema 混淆（Issue #9 已否） |
| Registry 按 task 发布、Database 仅远端 pin 列表 | Issue #11 明确 v1 不做；复杂度与 cache 一致性成本高 |
| Harbor Supabase 直耦合 | 难自托管；与「registry 可选」冲突 |
| 长期 dual-read 旧单包布局 | 禁止长期双权威；迁移成本一次付清 |
| Suite 合成 PASS | 破坏 evaluator 独立权威 |

## Assumptions

- 产品决策已在 2026-08-05 用户对齐会话确认（见 History）；**改 `docs/` / `src/` 仍需用户显式授权实现**。
- Spec 19 ACP 收口与本 epic **无硬依赖**；suite 验收可用 mock / 已有 L0 executor。
- 本机/CI 可提供 Docker（registry e2e 用 Postgres/RustFS 容器）；纯 format Spec 不依赖 Docker。
- Issue #7 在 Spec 21 实施收口时标记 duplicate / 指向 #11。

## History

| Date | Change | Reason |
| --- | --- | --- |
| 2026-08-05 | 初稿：从 Issue #9–#12 收敛为绑定决策 + Spec 映射 | 用户要求决策文件 + 若干 Spec 供审查；不改 Roadmap、不提交 |
| 2026-08-05 | 收紧 D2（database_id 字符集、defaults 仅调度键）、D6.8 默认 private；对齐 Critic blocking | 规划审查 subagent 指出签字前契约缝 |
| 2026-08-05 | 用户对齐 #1–#6：一次性迁移；defaults 方案 A；强制 `--task` 至 Spec 22；HTTP API + 可配置端点（本机开发 / 线上自部署）；suite FAIL 不取消其余；不写 Roadmap | 用户会话确认 |
| 2026-08-05 | Examples 验收布局：`examples/{core,journeys,l1}` 各为一个 Database；原包目录降为 `tasks/<task_id>/` | 用户明确最终验收形态 |
| 2026-08-05 | D6.10：收敛 v1 工程默认（RustFS、`services/registry`、`bora tasks`、example/* id、summary 路径、`BORA_REGISTRY_URL`） | 用户要求去掉「xx 或 yy」未决路线 |
