# Campaign 与 Suite

| | 命令 | 含义 |
| --- | --- | --- |
| 单 Attempt | `ageval run <dataset> --task <id>` | 一题一次 |
| Suite | `ageval run <dataset>`（无 `--task`） | 全成员 |
| Always-k | `ageval run … -k N` | 每题 N 次；CLI/job only，不是 yaml 字段 |
| Campaign | `ageval campaign <dataset> --task a --task b --matrix …` | 参数格点；一格失败其它格仍在 |

退出码：全 PASS = 0，否则 1。禁止 dry-run 冒充完成。

```text
suite job
  .ageval/suite-runs/<id>/
    summary.json    metrics.pass_rate / pass_at_k（观测）
    progress.json
    task_refs[]     run_id / attempt_run_ids
```

Hub Leaderboard 吃的是 **suite** 上传（`ageval results upload-suite`），不是单 Attempt `results upload`。公开榜还要完备且绑定 release。draft / 不完备只上 Jobs。

`--agent` 与 `--profiles` 互斥。Campaign 不与 `run.py` 内 scheduler 合并。
