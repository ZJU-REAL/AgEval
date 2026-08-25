# Evidence

布局字符串只出现在 `src/ageval/evidence/`。结构与数据流见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。

单次 Attempt：`<dataset>/.ageval/runs/<attempt_id>/`

| 文件 | 含义 |
| --- | --- |
| `lock.json` | 无 secret 的 lock 摘要 |
| `result.json` | 扁平 Result（status/score/kind/logs） |
| `trajectory.jsonl` | 层 C；`trajectory_seal` 独占槽默认引擎写 |
| `summary.json` | 相位事实 / timing；可选根字段 `extra`（Attempt 级观察袋，空则省略） |
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

层 C 按 invoke 序（Attempt 内 `seq` / `turn_index`）写成一个文件。每一行带一等 `profile_id`：这是 package role（`Agent.session(profile_id)`），不是 chat `role`（user/assistant）。同一 invoke 的 user / tool / assistant / terminal 共用该值。Hub / Viewer 按文件序展示，用 `profile_id` 区分是谁在说话，**不**按 role 重分组。旧 jsonl 若只有 `terminal.metadata.profile_id`，读侧按 `turn_index` 回填到该轮其它行。

## 层 C `terminal.usage`

对齐 ATIF 的拆法：一等 token/cost 在 turn 上，厂商剩余进袋子。密封后的 `terminal` 行：

```text
usage: { prompt_tokens, completion_tokens, cached_tokens, cost_usd }  # 一等；未知则省略
extra: { ... }                                                       # 兄弟字段：厂商 leftover + 插件袋
```

规则：

- 一等字段只在后端报告了该量时出现。后端没给就省略；**不要**编造 0 去冒充测过。
- `extra` 是 JSON-safe 标量/对象。未知键留在 `extra`，不升格为一等（升格要另改设计）。
- 典型袋子：`reasoning_tokens`、cache-write、厂商 `id`、ACP 的 `context` / `sources` / 非 USD `cost`、以及插件自写的键。
- `trajectory_collect` / `trajectory_enrich` 可以在 payload 的兄弟字段 `extra` 增补或合并键；不得删自己不拥有的一等 usage 字段。invoke 这袋 **不开新槽**（没有 `trajectory_extra` / `hub_display`）。
- `trajectory_seal` 仍是层 C 的作者；collect/enrich 只塑 payload。`turn_rows` 把 `usage` 与兄弟 `extra` 拷到 `terminal`，不得丢掉 `extra`。
- `openai-http` 从 Chat Completions `usage` 映射：`prompt_tokens` / `completion_tokens`（或 text tokens）/ `cached_tokens`（cached prompt tokens）。`AgentResult.usage` 与层 C 同一形状。
- ACP 保持现有双源（`PromptResponse.usage` + `usage_update`），已知量映到一等名；cache-read / cache-write 等剩余进 `extra`，不丢。

## Attempt `summary.extra`

两只观察袋、两档粒度。invoke 袋是密封 `terminal` 的兄弟字段 `extra`。Attempt 袋是 `summary.json` 的根字段 `extra`：

```text
extra: { <plugin_id>: { ... }, ... }   # 空则省略整键；默认 = 旧 summary 形状
```

规则：

- 观察袋，不是 PASS。Core **不**把 invoke 的 `terminal.extra` 聚合成 `summary.extra`（插件若要读 jsonl 自己读）。
- 链槽 `summary_enrich`（fail-open，形状 `(ctx, value, nxt)`）在 `trajectory_seal` 成功之后 emit **一次**；`value` 是这只袋，引擎起点 `{}`。插件只写自己的 `extra[<plugin_id>]`，不得删自己不拥有的键。
- 不复用 `trajectory_collect` / `trajectory_enrich`（每 invoke）、`trajectory_seal`（层 C 独占作者）、`after_run` / `after_evaluate`、`cleanup_report`。
- Core 把合并后的袋写入 `summary.json`；空袋不写 `extra` 键。
- Hub / Viewer 在 attempt / job summary 上投影折叠 JSON；没有袋就没有这块 chrome。不为此开 `hub_display`，不加 CLI 旗。`ageval plugin install` 仍不改 profiles。opt-in 走 `extensions`。

## `terminal.elapsed_ms`

invoke 墙钟写在 invocation `metadata.json` 的 `latency_ms`，并进入 `terminal.metadata.latency_ms`。折叠时：该 turn 的事件若还没给 `terminal.elapsed_ms`，则把 invoke `latency_ms` 拷过去。轨迹卡片读 `elapsed_ms`。

## 密封后的默认可持久集合

层 A/B 在 invoke 时照写（record 的 collect 仍读 `events.jsonl` + request）。`trajectory_seal` **成功之后**，默认磁盘与 Hub archive 只留：

```text
lock.json
result.json
trajectory.jsonl
summary.json
task-artifacts/**
```

`summary.json` 是相位墙钟，不是 vendor raw。Verifier 看 `result.json`；默认不留 `evaluation/evaluator_raw.json`。

`--keep-vendor-raw`（默认关）才保留 `backend_raw/`、per-invoke `request.json` / `events.jsonl` / `final-response.json` / `metadata.json`、失败 `stderr.txt`、`agent/events.jsonl`、`evaluator_raw.json`。`--keep-workspace` 只管宿主 work root（`l1-work`），与 vendor raw 无关。`ageval evidence` 跟可持久树走，层 C 优先。只作用于新 run，不改写旧树。删文件不是 PASS。

lock 与 evidence 禁止 host token。密钥 locator 只留名字。

Suite：`<dataset>/.ageval/suite-runs/<id>/summary.json`（`pass_rate` 等是观测，不是 suite PASS）。
