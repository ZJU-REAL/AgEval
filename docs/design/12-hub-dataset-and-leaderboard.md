# 12 — Hub Dataset 可见性与 Leaderboard 完备性

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件是 Dataset draft/release、dataset ACL、Leaderboard 完备性、suite 插件出处、个人主页过滤与 Hub/Viewer chrome 的机制权威 |
| 摘要 | Dataset 按工作树 + 不可变 release 维护；公开榜只排完备且绑定 release 的 suite；写路径只在 CLI。Leaderboard 展开分 profiles / plugin；插件页是声明槽时间线；个人主页按 uploader / ACL 聚合。 |

---

> [!important] 设计决定
> Dataset 在 Registry 上按 git 隐喻维护：**一份可覆盖的 draft** 与 **不可变 releases**。ACL 在 dataset 上，不在 task 上。Hub 是只读操作面，不提供 publish / upload / release 按钮。
> Leaderboard 行是**完备的 suite 跑次**，不是 suite-level PASS。缺题结果不上榜；题上 FAIL 仍算完备。公开榜只收绑定 **release** 的完备 suite；draft 绑定行只出现在 Jobs。

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

| 表面 | 谁出现 |
| --- | --- |
| Public Leaderboard | `complete` 且 `bound_kind=release` |
| Task Jobs | 调用者可见的全部 suite（含 incomplete、draft-bound） |

过滤在 Registry list API（`board=1`），不靠 SPA 藏行作为唯一门。

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

本地 Viewer 绑定**一个** Database 根，不连 Registry。

- `bora view --dev` 只起 API，不要求预构建 SPA；Vite 源是 UI。两进程契约：API 端口 + UI 端口。
- CLI 接受打开路径（job / task / run），深链到同一套客户端路由。
- Jobs 列出该根下的 suite-run **和** 单题 Attempt（database 级与 task-local `.bora/runs`）；用 `source_kind` 区分。不扫描其它 Database。

## 非目标

- Hub GUI 写操作（publish / upload-suite / release 按钮）
- per-task ACL、多份 named draft
- suite-level PASS 权威
- Viewer 跨 Dataset 扫描
- 证据等级升级
- Leaderboard 条内嵌 L0–L5 时间线（时间线只在插件详情）
- 按 job 实际走过的槽画执行图（需要 run evidence，不是声明槽）
