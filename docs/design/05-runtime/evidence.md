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

层 A/B 是 invoke 期的 scratch；层 C 是 Hub / Viewer / `ageval evidence` 的观察记录。轨迹不是分数，也不绑定 PASS。

## 层 C `terminal.usage`

对齐 ATIF 的拆法：一等 token/cost 在 turn 上，厂商剩余进袋子。密封后的 `terminal` 行：

```text
usage: {
  prompt_tokens, completion_tokens, cached_tokens, cost_usd,  # 一等；未知则省略
  extra: { ... }                                              # 厂商 / 插件袋子
}
```

规则：

- 一等字段只在后端报告了该量时出现。后端没给就省略；**不要**编造 0 去冒充测过。
- `extra` 是 JSON-safe 标量/对象。未知键留在 `extra`，不升格为一等（升格要另改设计）。
- 典型袋子：`reasoning_tokens`、cache-write、厂商 `id`、ACP 的 `context` / `sources` / 非 USD `cost`、以及插件自写的键。
- `trajectory_collect` / `trajectory_enrich` 可以在 `usage.extra` 增补或合并键；不得删自己不拥有的一等字段。**不开新槽**（没有 `trajectory_extra` / `hub_display`）。
- `trajectory_seal` 仍是层 C 的作者；collect/enrich 只塑 payload。`turn_rows` 把 `usage`（含 `extra`）原样拷到 `terminal`，不得丢掉 `extra`。
- `openai-http` 从 Chat Completions `usage` 映射：`prompt_tokens` / `completion_tokens`（或 text tokens）/ `cached_tokens`（cached prompt tokens）。`AgentResult.usage` 与层 C 同一形状。
- ACP 保持现有双源（`PromptResponse.usage` + `usage_update`），已知量映到一等名；cache-read / cache-write 等剩余进 `extra`，不丢。

## `terminal.elapsed_ms`

invoke 墙钟写在 invocation `metadata.json` 的 `latency_ms`，并进入 `terminal.metadata.latency_ms`。折叠时：该 turn 的事件若还没给 `terminal.elapsed_ms`，则把 invoke `latency_ms` 拷过去。轨迹卡片读 `elapsed_ms`。

lock 与 evidence 禁止 host token。密钥 locator 只留名字。

Suite：`<dataset>/.ageval/suite-runs/<id>/summary.json`（`pass_rate` 等是观测，不是 suite PASS）。
