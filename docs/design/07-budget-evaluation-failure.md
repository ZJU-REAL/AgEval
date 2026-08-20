# 07 — 硬顶与失败

硬顶由 Runtime 在效果前强制：`limits.wall_time_seconds`、`limits.agent_invocations` 等。值为 0 表示不得 attach。题包软限（max_turns）不能替代硬顶。事后 token/cost 只作观测。

完整失败归属表：[ARCHITECTURE.md](../../ARCHITECTURE.md) § Failure and Privacy Boundary。

| 退出码 | 含义 |
| --- | --- |
| 0 | PASS；或 `--probe` ready |
| 1 | FAIL；或 probe 不可跑 |
| 2 | ERROR / 配置 / 运行时 |

| 失败类 | 表现 | 归属 |
| --- | --- | --- |
| 未知 format | `invalid_format` `/format` | Config |
| 缺 cap / inject | lock 失败 | Config / plugins |
| 缺钥 | preflight 一次失败，`started: false` | 盒子 / executor |
| 评测低分 | FAIL + score | Evaluation |
| Evaluator 崩 | `error.phase = evaluate` | Evaluation |
| Cleanup 失败 | warning | 不改已 bind 的分 |

相位失败记在该 phase。未知键：拒绝，一条消息。不要把 skip 写成通过。
