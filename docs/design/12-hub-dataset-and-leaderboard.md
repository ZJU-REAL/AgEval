# 12 — Hub Dataset 可见性与 Leaderboard 完备性

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件是 Dataset draft/release、dataset ACL、Leaderboard 完备性、suite 插件出处、个人主页过滤与 Hub/Viewer chrome 的机制权威 |
| 摘要 | Dataset 按工作树 + 不可变 release 维护；公开榜只排完备且绑定 release 的 suite；写路径只在 CLI。Leaderboard 展开分 profiles / plugin；Runtime plaza 用 binding.overlays 连接包文件预览（不随 suite 再传字节）；插件页是声明槽时间线；个人主页按 uploader / ACL 聚合。 |

---

> [!important] 设计决定
> Dataset 在 Registry 上按 git 隐喻维护：**一份可覆盖的 draft** 与 **不可变 releases**。ACL 在 dataset 上，不在 task 上。Hub 是只读操作面，不提供 publish / upload / release 按钮。
> Leaderboard 行是**完备的 suite 跑次**，不是 suite-level PASS。缺题结果不上榜；题上 FAIL 仍算完备。公开榜只收绑定 **release** 的完备 suite；draft 绑定行只出现在 Jobs。
> 本地 Viewer 可删除**当前打开的** Database 根下的 Job 树（suite 始终级联 Attempt）。这不是第二条 Control Plane，也不写 Hub / Registry。

## Dataset：draft 与 release

| 槽 | 语义 |
| --- | --- |
| **draft (current)** | 每个 `database_id` 恰好一个当前 draft；CLI 上传覆盖；不是 release |
| **release** | owner 从当前 draft 固化出的不可变版本；坐标仍是 `database_id@version` |

硬规则：

1. 保留字 `draft` 不得作为 release 的 `version`。
2. 后写 draft **不得**改写已发布 release 的 blob 或 task 集。
3. 没有多份 named draft，也没有 draft 历史。
4. Plugin 包不走 draft 槽；`package_kind=plugin` 仍直接发 release。
5. Hub **不**提供写按钮。CLI 是唯一写路径。

## Dataset ACL

ACL 挂在 `database_id` 上（不是 per-task）。

| 主体 | 读 draft | 覆盖 draft | 发布 release |
| --- | --- | --- | --- |
| dataset owner | 是 | 是 | 是 |
| dataset collaborator | 是 | 是 | 否 |
| 所属 org 成员 | 是 | 否 | org owner 可发 |
| 其他人 / 未登录 | 否（404 / 省略，与 private 包同一风格） | 否 | 否 |

首次 draft 上传：调用者必须是 `--org` 成员，并成为该 Dataset 的 owner。

版本列表：

- 有权读者：`draft` 行（`slot=draft`，UI 文案 `draft (current)`）+ 各 release
- 无权读者：仅可见 release

`GET …/versions/draft` 对无权调用返回 **404**，不泄露 draft 是否存在。

## Leaderboard 完备性

**Complete** = 该 suite **绑定版本** 的每一个 task 都有一条 result。

绑定版本在上传时确定：

1. 声明的 `database_version` 若已是一条 release → `bound_kind=release`
2. 否则若该 Dataset 有 draft → `bound_kind=draft`
3. 否则 `bound_kind=unknown`（不上榜）

task 集指纹在上传时从绑定版本的包归档提取并落库。之后改 draft **不**回写历史 suite 行，因此给较新 draft 加题不会把旧的完备 **release** 跑次踢下榜。

判定：

- 题上 **FAIL** / **ERROR** / **PASS** 都算「有 result」
- 缺行或无 status 且无 score → incomplete
- `n_attempts` 不对齐 **不**取消资格
- Complete **不是** suite PASS；指标仍是观测值
- 点名换槽后的 suite **仍按现行指针**判定完备；`previous[]` 不参与完备、也不进 `pass_rate` / `mean_score` / `pass@k` / `pass^k`
- `amended: true` 只作审计。**不得**仅因某槽被换过就把该行踢出 Public Leaderboard

| 表面 | 谁出现 |
| --- | --- |
| Public Leaderboard | `complete` 且 `bound_kind=release` |
| Task Jobs | 调用者可见的全部 suite（含 incomplete、draft-bound） |

过滤在 Registry list API（`board=1`），不靠 SPA 藏行作为唯一门。

### Suite `task_refs`：现行指针与槽历史

每个评分槽一条链：`run_id`（及 Always-k 的 `attempt_run_ids`）是**现行** Attempt；被换下的现行收进该槽 `previous[]`（oldest → newest superseded）。v1 没有整份 suite 快照版本。

| 字段 | 语义 |
| --- | --- |
| `run_id` / `attempt_run_ids` | 现行样本。Hub / Viewer 默认打开这些。 |
| `previous[]` | 该槽被换下的 Attempt 瘦记录（`run_id`、`status`、`score`、`attempt_index`、`started_at`、`replaced_at`）。无历史则省略。`started_at` 是该 Attempt 的开始时间，不是 suite 换槽时刻。 |
| `status` / `score` / `n` / `c` | **只**由现行样本计算。 |

Hub / Viewer 打开 suite 题 / run 时默认现行。操作者用同一套 shadcn `Select` 只读切版本：列表文案是 `patch N` + 该 Attempt 的开始时间，**不**把 `run_id` / digest 写进菜单。内部仍按 `run_id` 打开证据。**没有** GUI 写（上传 / 换槽 / 回滚整份 suite）。

写路径只在 CLI + Registry：本地 `--resume-suite --replace-slot` 之后，上传**新** Attempt 并对已有 `suite_run_id` PATCH 一槽。`upload-suite --replace` 仍是整行覆盖、不留 `previous[]`，换槽不得走它。旧 Attempt blob 保留，直到独立的 delete。

## Leaderboard 行展开：profiles | plugin

行展开是只读条，**不是** Attempt 证据浏览器。

| Tab | 内容 |
| --- | --- |
| **profiles** | 无密钥的 `job_overlay` YAML + `bora results export-profiles` 再跑命令 |
| **plugin** | 该 job 用到的插件（`plugin_id` + 可选 `version`）；点击进 marketplace 详情 |

插件名单来自上传播要的 secret-free `plugins` 列表；缺省时可由 `job_overlay.bindings.*.executor` 推断（排除内建 `acp` / `openai-http`）。**不**在条里画 L0–L5 时间线。名单不得含密钥或 host env。

## 插件详情：声明槽时间线

Plugin 页把 provide/on chips 换成 **L0–L5 声明槽时间线**：

- 节点顺序固定 L0…L5；本插件 `provide` / `on` 命中的层高亮，未命中层静默可见。
- 展开：槽名、短说明、跳到**已有**包内文件树预览（实现 `entry` 能对上路径时；否则 `plugin.yaml`）。
- 时间线是 **manifest 声明**，不是某次 job 的执行轨迹。浏览器不执行插件代码。

## 个人主页

登录用户有只读聚合页（账号入口）。未登录进登录，不造空主页。

| 段 | 过滤 |
| --- | --- |
| Jobs | `uploaded_by` = 当前用户（不是「所属 org 的全部 job」） |
| Organizations | 成员关系（已有 list orgs） |
| Datasets | 该用户在 dataset ACL 上为 owner / collaborator |
| Tasks | 上述可维护 Dataset 的 task 成员 |
| Plugins | 当前用户上传的 `package_kind=plugin`（`uploaded_by`） |

列表过滤在 Registry（`uploaded_by=me`、`mine=1`），不把全库拉到浏览器再筛。本页无 publish / upload / release 按钮。

## Hub / Viewer chrome

不新增产品对象：

1. Datasets / Plugins 等同一套列表：搜索框与 **Your organizations | Explore** 同一行、靠右。
2. 文件树/预览分栏高度固定为面板上限；短树底部留白，不塌缩、不跳布局。
3. 轨迹里每个 **tool-call**（及其他过长行）可折叠；Hub Attempt 与本地 Viewer 行为一致。只改呈现，不改 PASS / 证据内容。

## 本地 Viewer（操作面）

本地 Viewer 绑定**一个** Database 根，不连 Registry。Hub 的写路径（publish / upload / release）仍只在 CLI；本地 Viewer **不是**第二条 Control Plane。

- `bora view --dev` 只起 API，不要求预构建 SPA；Vite 源是 UI。两进程契约：API 端口 + UI 端口。
- CLI 接受打开路径（job / task / run），深链到同一套客户端路由。
- Jobs 列出该根下的 suite-run **和** 单题 Attempt（database 级与 task-local `.bora/runs`）；用 `source_kind` 区分。不扫描其它 Database。

### 本机 Job 删除

操作者可从 Jobs 列表删除**一行**本地 Job。删除是擦除该 Database 根下的证据树，不是改 `result.json`、分数或 PASS。同一 `run_id` / `suite_run_id` 若已上传到 Hub，Registry 行是另一对象，本地删除不调用 Registry。

| 动作 | 磁盘 | 之后 |
| --- | --- | --- |
| 删除 `source_kind=single` | 该 Attempt 树：`<db>/.bora/runs/<run_id>/` 或 `tasks/<id>/.bora/runs/<run_id>/` | 该行消失；其它 Job 不动 |
| 删除 `source_kind=suite` | suite 树 **以及它引用的每一个 Attempt**（`task_refs` / `attempts[]` / `attempt_run_ids`） | suite 与这些 Attempt 都消失；**不得**再以 single 回流 |
| 从 suite 内删一条 Attempt | **拒绝** | 只能删整行 suite Job，或什么都不删 |

级联是 suite 删除的**唯一**行为，不是开关。没有「只删 suite 元数据」的路径。

硬规则：

1. 二次确认：先 preview（相对路径、字节数、将删除的 `run_id`），再确认。CLI 对等入口需要显式 `--yes`。
2. suite 仍在进行（`progress.json` 未结束，或 `cancel.requested` 仍在）→ 拒绝。
3. 引用的 Attempt 仍被**另一尚未删除的** suite 认领 → 拒绝（不得静默偷走）。
4. 路径逃逸（`..`、多段 id）→ 拒绝。路径字符串由 evidence locator 拥有（`.bora/runs/`、`.bora/suite-runs/`）。
5. Preview / 删除载荷不得含密钥或 host 绝对路径。
6. 不重算 suite 指标；没有「去掉一条 Attempt 再改 `summary.json`」。
7. `l1-work/`（`--keep-workspace` 残留）不在本操作范围内。

同一 Application 用例同时服务 Viewer HTTP 与 CLI。HTTP 只路由。

## Runtime plaza（派生）

Hub `/runtimes` 是官方公开、完备、**release-bound** Leaderboard suite 的派生视图。**不**存 Runtime 行。身份是 agent 产品（ACP `options.entry`，否则插件 executor）。运输层 `acp`、model、凭据、`label`、role、组队 **不是** plaza id。`rt_*` **不得**哈希 overlay 路径或文件字节。

`GET /v1/runtimes/{id}` 的每条 appearance 带绑定 release 坐标：`database_id`、`database_version`、`package_digest`（或 suite 行上已有的等价字段）。Hub 用已有

`GET /v1/packages/{database_id}/by-digest/{digest}/files` 与 `…/files/{path}`

打开 Dataset 包内文件。**不**新增 Runtime 表，**不**提供 `/v1/runtimes/{id}/files`。

详情页：

1. Header + 无密钥 profiles YAML（含该出场 binding 的 `overlays:`）。
2. 选中 Results 行 → 该 role `overlays:` 的前缀闭包。
3. 复用 Dataset / Plugin 页的文件树分栏（`FileSplitPanel`）。
4. 换行换树。一个 `rt_*` 可对应多棵树。该 binding 省略 `overlays` → 无树（只 YAML）。

`bora results upload-suite` 继续只上传 secret-free `job_overlay` JSON（现含 `bindings.*.overlays` **路径**）。**不**把 overlay 字节打进 suite archive。字节留在 suite 绑定的官方 Dataset **release**。Hub 只读，无写按钮。两 role 列同一路径时 Dataset 仍是一份 blob。`bora results export-profiles` 写回 `overlays:`；再跑仍要 Database 里那些相对路径上的文件，Hub 不另下一份。

同一套声明列表也出现在 Dataset **Overlays** tab、Task Files 的 Overlays 范围、Leaderboard 展开的 profiles 条，以及本地 Viewer 的 suite Job 详情。仍走已有包文件 / Database 根预览，不新建 Runtime files API。

## 非目标

- Hub GUI 写操作（publish / upload-suite / release 按钮）
- 经 Viewer 删除 / 改可见性 Registry 行
- per-task ACL、多份 named draft
- suite-level PASS 权威
- Viewer 跨 Dataset 扫描
- 证据等级升级
- Leaderboard 条内嵌 L0–L5 时间线（时间线只在插件详情）
- 按 job 实际走过的槽画执行图（需要 run evidence，不是声明槽）
- 软删除回收站 / 事后 gc；v1 是确认后的硬删除
- 从插件 `options` / `src` 推断 plaza 发布树
- 把 overlay 字节随 suite 再上传，或新 Runtime files API
- 把 overlay 路径或内容摘要打进 plaza `rt_*` 或 suite `config_fingerprint`
