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

## 市场收藏

`favorite_count` 按 `dataset_id` 累计，不是 per-version。每人每个包最多一条收藏。只允许 **plugin** 与 **agent**（dataset 拒绝）。列表与 by-digest meta 带 `favorite_count`（缺记录为 0）；已登录调用方另带 `favorited`。

- `POST /v1/packages/{id}/favorite`：登录后收藏；须能看见该包。已收藏则幂等返回当前状态。
- `DELETE /v1/packages/{id}/favorite`：取消收藏；未收藏也幂等。
- `GET /v1/packages?favorited=1`：只列当前用户收藏且仍可见的包。无登录用户 id 则空列表。

Hub：plugin / agent 卡片与详情把 `favorite_count` 与 `download_count` **同一行**展示。`/plugins` 与 `/agents` 的 scope tab 为 **Your organizations | Explore | Favorites**（dataset 列表不加 Favorites）。未登录点收藏去登录页。

## 组织成员顺序

`GET /v1/orgs/{id}/members` 的 `items`：**owner 在前**，同角色按 `user_id`。Hub 成员表按该顺序渲染。
