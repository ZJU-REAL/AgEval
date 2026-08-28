# 12 — Hub 与 Registry

字段是 `dataset_id`。无 `database_id` 双读。Hub / Viewer 文案用 dataset，不是 Database。无 `ageval submit`；上传走 `ageval results upload` / `upload-suite`。

公开 Leaderboard：完备 suite + 绑定 **release** + Dataset 包所属 org 的 owner 批准 listing（`board_listed`）。官方与非官方 Dataset 同一道门。`public` 不是上榜：可见性与 listing 分开。新上传默认未列出；listing 加上去之后，库里已有的 suite 也不会自动出现在公开榜上。Internal（调用方可见的不完备 / draft-bound）不变。公开 / Internal 默认列出该 Dataset 下全部已过上榜条件的 suite，不跟页顶版本走（`?v=` 只切 README / Tasks / lock 命令）。Public 右侧另有版本 Select：默认 All versions；`?dataset_version=` 按 suite 上传时带的 `dataset_version` 过滤。过滤不是新的上榜条件，也不改 listing / fingerprint / PASS。

单 Attempt `results upload` 通常上不了榜。正确路径：`ageval run <dataset>`（无 `--task`）→ `ageval results upload-suite --suite-run <id> --with-attempts`。申请人是 suite `uploaded_by`；不完备或 draft-bound 申请 listing fail closed。批准只写 listing 标记，不改 lock / fingerprint / overlay。

`--agent` 投影进 profiles 通道，与 `--profiles` 互斥。`agent_ref` 是 harness 溯源不是身份，不进 `config_fingerprint`（机制卡 vs 定制卡与 `--model` 见 [14](14-agent-hub.md)）。已上传 suite 允许延后把 published `org/name@version` 写入 **Registry 存的** `job_overlay`。Appearances 对齐尺子：executor + ACP entry（**不含** model，也不含其余 secret-free plugin options；`reasoning_effort` 等同 model 的 run 参数）。suite 可比性仍走 `_binding_role_key`（含实际 model 与 options）。不改 Attempt `lock.json`、digest、PASS。`local/` 与 `file:` 不能当 Hub 溯源。plaza 出场（官方 Dataset + public + complete + release）不变。

机制卡（builtin 短 id）的已登记 model 从 plaza overlay 按 `resolve_agent_id` 归堆，**不**经 Agent org 同意。定制 upload 包的 Appearances 仍要该包 org 同意：owner 自己 attach，或批准 `agent_appearance` 请求。Leaderboard 上榜门（listing）不因此放宽。

Leaderboard 两列保持 Harness / Model。plaza 行上的 `agent_refs` 变链：机制卡短 id（`--agent pi` / attach `pi`）不经 Agent org 同意；定制 `org/name` 仍要同意。Harness 打开 `/agents/{package_id}`，Model 打开同一 harness 页 `?model=`（overlay `model`）。无 ref 则两列都是观测文本，不要按 executor / overlay 文案猜包。不要 `/agents/…/models/…`。Environment 仍是机制标。

Inbox：Registry 一等 request 行（`pending` / `approved` / `rejected`）。两种 kind：`leaderboard_list`（收件人 = Dataset org owner）、`agent_appearance`（收件人 = Agent 包 org owner）。批准只跑已有写入（listing 标记，或同一条 attach 路径）。申请人已是该 Agent org owner 时出场走 attach、不建请求。加入 org 仍是 invite key。

## 身份页

公开用户 `GET /v1/users/{user_id}`：`user_id` 即 GitHub login。`display_name` / `avatar_url` 来自登录快照，不是 Hub 可写字段。Hub 可写的只有 `description`（`PATCH /v1/users/{user_id}`，仅本人）。主页用 `https://github.com/{user_id}` 作为 GitHub 链，不另存 URL。

组织：`display_name` 与可选 `description`。owner `PATCH /v1/orgs/{id}` 可改其中任一；创建时可带 `description`。

未知键拒绝。空 description 表示清除。

## 市场下载量

`download_count` 按 `dataset_id` 累计，不是 per-version，也不是 PASS / 安装成功。每次成功 `GET /v1/packages/{id}/by-digest/{dig}/content`（真 blob，不是 `/files` 预览）加一。列表与 by-digest meta 都带该字段（缺记录为 0）。Hub 在 plugin / agent 卡片与详情展示；dataset 表不展示。

## 市场收藏

`favorite_count` 按 `dataset_id` 累计，不是 per-version。每人每个包最多一条收藏。只允许 **plugin** 与 **agent**（dataset 拒绝）。列表与 by-digest meta 带 `favorite_count`（缺记录为 0）；已登录调用方另带 `favorited`。

- `POST /v1/packages/{id}/favorite`：登录后收藏；须能看见该包。已收藏则幂等返回当前状态。
- `DELETE /v1/packages/{id}/favorite`：取消收藏；未收藏也幂等。
- `GET /v1/packages?favorited=1`：只列当前用户收藏且仍可见的包。无登录用户 id 则空列表。
- `GET /v1/packages?orgs=1`：只列调用方所属组织发布的包。无登录用户 id 则空列表。
- `GET /v1/packages?visibility=public`：只列公开包（Explore）。

Hub 列表 tab **就是**这些查询参数（不要再叠一层 `scope=`）。默认 Explore：

| URL | Tab |
| --- | --- |
| `/plugins`、`/agents`、`/datasets`（无额外参数或 `?visibility=public`） | Explore |
| `?orgs=1` | Your organizations（请求带 `orgs=1`） |
| `?favorited=1` | Stars（仅 `/plugins`、`/agents`） |

列表上的 star 是计数，不是写入口。写收藏只在包上；未登录走登录。组织详情的 settings 用 `?tab=settings`（默认 overview 省略 `tab`）。

## Dataset Tasks / Jobs 分页

Hub 表分页**就是**查询参数（不要再叠 `page=` 之外的 scope 层）。默认 `limit=20`，上限 `100`。`offset` 默认 `0`。响应带 `items`、`total`、`limit`、`offset`。

| URL / 请求 | 含义 |
| --- | --- |
| Dataset `?tab=tasks` | 第一页 Tasks |
| Dataset `?tab=tasks&offset=20` | 下一页；Hub 请求 `GET /v1/packages/{id}/by-digest/{dig}/tasks?limit=20&offset=20` |
| Task Jobs `?tab=jobs&offset=` | 该 task 的 suite/attempt 行 |

`GET /v1/packages/{id}/by-digest/{dig}/tasks` 读 publish 时按 `package_digest` 落下的任务摘要（`task_id`、`has_readme`），并返回 `has_shared` 与 `overlay_prefixes`。`overlay_prefixes` 来自包内全部 overlay 源文档（根 `profiles.yaml` 以及 `tasks/` 之外、basename 为 `profiles` / `profiles.*` 的 yaml），不是只读根文件。分页 item 另带观测字段 `job_count` / `last_status` / `last_score`（调用方可见 suite 的 `task_refs`，不是 PASS）。不把整棵文件树交给浏览器，也不为 Tasks 表拉全量 suite。未知查询键拒绝。缺失摘要时才回退 inflate 一次并写回。

`GET /v1/results/suites` 增加可选 `task_id`、`limit`、`offset`。省略 `limit` 时返回全量（兼容现有客户端）。`task_id` 按 suite `task_refs` 过滤。

README 预览不经过整包文件树闸门；其它区块按需拉取。不要为打开包就把文件树和 suite 一次拉完。

## 组织成员顺序

`GET /v1/orgs/{id}/members` 的 `items`：**owner 在前**，同角色按 `user_id`。Hub 成员表按该顺序渲染。

## 市场图标

Plugin / agent 的实体标默认是 **uploader 的 GitHub 头像**（`uploaded_by` 即 GitHub login）。Hub org **不是** GitHub org，不要用 `org_id` 去拼 `github.com/{org}.png`。

Owner `PATCH /v1/packages/{id}` 可改写（与 `display_name` 同权，不进 blob，不按 version）。只认这两个键：

| 字段 | 含义 |
| --- | --- |
| `icon_key` | 闭包目录 id。未知 key：**一条** `invalid_request` |
| `icon_github` | GitHub login。从 `github.com/{login}` 或 `github.com/{login}/{repo}` 取出 owner；非法 login 一条 `invalid_request` |

空字符串清除该字段。两个都空 = 回到 uploader 头像。一次 PATCH 可同时带两键（picker 保存时：选用录则清 github，填 link 则清 key）。

解析顺序：已存 `icon_key` → 已存 `icon_github` → `uploaded_by` 的 `https://github.com/{login}.png?size=64` → 字母占位。裂图走字母。不把图片字节写入 Registry。

闭包目录是 **彩色真实标**（官方 kit / Lobe static SVG / Simple Icons 路径 + 官方 hex）。禁止自造厂商 logo。黑标（ink，如 OpenAI）固定白底；白标（paper，如 Kimi）固定黑底。底板不跟主题反相。改标是包级写，不在列表卡上开 picker。Viewer 本轮不做。

机制标（Leaderboard Environment 的 `docker` / `e2b` 等）仍走闭包精确 id，不是 uploader 头像。
