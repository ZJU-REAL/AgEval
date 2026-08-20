# 12 — Hub 与 Registry

字段是 `dataset_id`。无 `database_id` 双读。Hub / Viewer 文案用 dataset，不是 Database。无 `ageval submit`；上传走 `ageval results upload` / `upload-suite`。

公开 Leaderboard：完备 suite + 绑定 **release**。draft 或不完备只出现在 Jobs。

单 Attempt `results upload` 通常上不了榜。正确路径：`ageval run <dataset>`（无 `--task`）→ `ageval results upload-suite --suite-run <id> --with-attempts`。

`--agent` 投影进 profiles 通道，与 `--profiles` 互斥。`agent_ref` 是溯源不是身份。
