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

`icon_key` 是包级展示字段，权和 `display_name` 相同：owner `PATCH /v1/packages/{id}`，不进 blob，不按 version。列表与 by-digest meta 都带该字段（未设置则省略）。空字符串清除。未知 key：**一条** `invalid_request`，不翻译、不模糊匹配。

两类用途，不要混：

| 用途 | 出现位置 | 谁决定 |
| --- | --- | --- |
| 实体标 | plugin / agent 卡片标题左侧、详情标题旁、Leaderboard Harness（agent `org/name`） | 已存 `icon_key`；否则按 `dataset_id` 叶、plugin slot、agent `options.entry` **精确别名**建议；再否则字母占位 |
| 机制标 | Leaderboard Environment 列；详情里 `environment:` / ACP `options.entry` | 闭集精确映射（`docker` / `e2b` / `claude` / `codex` / …）。包作者不能改成别的厂商 |

闭包目录在 Hub（`apps/hub/src/lib/brand-marks/`）：SVG 拷进仓，单色 `currentColor`。不把 Simple Icons / Developer Icons / Lobe Icons 当运行时组件库。详情页（仅 `canEdit`）点实体标打开可搜索 modal，只列出该目录；卡片整卡导航，不在卡上开 picker。v1 不接受自定义上传。Viewer 本轮不做。
