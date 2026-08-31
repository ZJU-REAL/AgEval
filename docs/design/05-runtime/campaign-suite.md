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

`summary.json` 在 suite 进行中就存在，是 **观测快照**：只统计已 settle 的 attempt，
`status` 为 `running` / `cancelling`，`metrics.pass_rate` =
`n_pass / (n_pass + n_fail + n_error)`（分母是已 settle 的任务，不是计划任务数）；
`tasks[]` / `attempts[]` / `task_refs[]` 只列已 settle 的工作，未跑的 task id 不出现。
它不是 suite PASS。suite 完成 / 取消时同一文件被按全计划 id 集重写为终值；
`created_at` 在首次写入时锁定，resume 重写不改写它。`progress.json` 仍是
slot / cancel 文档（计划数、in-flight、取消请求），两文件各管各的。

Viewer Jobs 对进行中的 suite 显示 **一行**（suite_run_id 唯一），pass rate 取自该
快照，Trials 显示 `settled / planned`；已 settle 的 run id 归属该 suite 行，
不再以单题 job 重复出现。`ageval results upload-suite` 拒绝 `running` /
`cancelling` 的快照——观测快照不是完备 suite，完备性门禁不变。

Hub Leaderboard 吃的是 **suite** 上传（`ageval results upload-suite`），不是单 Attempt `results upload`。公开榜还要完备且绑定 release。draft / 不完备只上 Jobs。

`--agent` 与 `--profiles` 互斥。`--model` 须配合 `--agent`（`lock` / `run` / `campaign`）。Campaign 不与 `run.py` 内 scheduler 合并。
