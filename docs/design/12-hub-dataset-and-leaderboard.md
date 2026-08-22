# 12 — Hub 与 Registry

字段是 `dataset_id`。无 `database_id` 双读。Hub / Viewer 文案用 dataset，不是 Database。无 `ageval submit`；上传走 `ageval results upload` / `upload-suite`。

公开 Leaderboard：完备 suite + 绑定 **release**。draft 或不完备只出现在 Jobs。

单 Attempt `results upload` 通常上不了榜。正确路径：`ageval run <dataset>`（无 `--task`）→ `ageval results upload-suite --suite-run <id> --with-attempts`。

`--agent` 投影进 profiles 通道，与 `--profiles` 互斥。`agent_ref` 是溯源不是身份。

## 身份页

公开用户 `GET /v1/users/{user_id}`：`user_id` 即 GitHub login。`display_name` / `avatar_url` 来自登录快照，不是 Hub 可写字段。Hub 可写的只有 `description`（`PATCH /v1/users/{user_id}`，仅本人）。主页用 `https://github.com/{user_id}` 作为 GitHub 链，不另存 URL。

组织：`display_name` 与可选 `description`。owner `PATCH /v1/orgs/{id}` 可改其中任一；创建时可带 `description`。

未知键拒绝。空 description 表示清除。

## 市场下载量

`download_count` 按 `dataset_id` 累计，不是 per-version，也不是 PASS / 安装成功。每次成功 `GET /v1/packages/{id}/by-digest/{dig}/content`（真 blob，不是 `/files` 预览）加一。列表与 by-digest meta 都带该字段（缺记录为 0）。Hub 在 plugin / agent 卡片与详情展示；dataset 表不展示。

## 市场图标

Plugin / agent 的实体标默认是 **uploader 的 GitHub 头像**（`uploaded_by` 即 GitHub login）。Hub org **不是** GitHub org，不要用 `org_id` 去拼 `github.com/{org}.png`。

Owner `PATCH /v1/packages/{id}` 可改写（与 `display_name` 同权，不进 blob，不按 version）。只认这两个键：

| 字段 | 含义 |
| --- | --- |
| `icon_key` | 闭包目录 id。未知 key：**一条** `invalid_request` |
| `icon_github` | GitHub login。从 `github.com/{login}` 或 `github.com/{login}/{repo}` 取出 owner；非法 login 一条 `invalid_request` |

空字符串清除该字段。两个都空 = 回到 uploader 头像。一次 PATCH 可同时带两键（picker 保存时：选用录则清 github，填 link 则清 key）。

解析顺序：已存 `icon_key` → 已存 `icon_github` → `uploaded_by` 的 `https://github.com/{login}.png?size=64` → 字母占位。裂图走字母。不把图片字节写入 Registry。

闭包目录是 **彩色真实标**（官方 kit / Lobe static SVG / Simple Icons 路径 + 官方 hex）加少量 **通用** 几何标。禁止自造厂商 logo。详情页（`canEdit`）点标打开 modal：搜目录，或填 GitHub link。卡片整卡导航，不在卡上开 picker。Viewer 本轮不做。

机制标（Leaderboard Environment 的 `docker` / `e2b` 等）仍走闭包精确 id，不是 uploader 头像。
