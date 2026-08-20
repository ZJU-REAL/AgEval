# Evidence

布局字符串只出现在 `src/ageval/evidence/`。结构与数据流见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。

单次 Attempt：`<dataset>/.ageval/runs/<attempt_id>/`

| 文件 | 含义 |
| --- | --- |
| `lock.json` | 无 secret 的 lock 摘要 |
| `result.json` | 扁平 Result（status/score/kind/logs） |
| `trajectory.jsonl` | 层 C；`trajectory_seal` 独占槽默认引擎写 |
| `summary.json` | 相位事实 / timing |
| `agent/` | invoke 级观察 |

`Result.logs` / `evidence_path` 指向该树。

轨迹是观察事实，不是分数。export：`ageval evidence <logs> --out …`（再脱敏，不改分）。

三层：

```text
A  vendor raw     后端原样
B  中立事件       ageval.trajectory.event/1（adapter 只映射）
C  trajectory.jsonl  `trajectory_seal` 赢家写（默认引擎折叠）
```

lock 与 evidence 禁止 host token。密钥 locator 只留名字。

Suite：`<dataset>/.ageval/suite-runs/<id>/summary.json`（`pass_rate` 等是观测，不是 suite PASS）。
