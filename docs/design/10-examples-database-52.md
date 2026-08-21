# 10 — 点名示例

这里不是进度表。

必须能 `ageval lock`（有凭证则 run）的包：

| 包 | 点名 |
| --- | --- |
| `examples/core` | `acp-local-min`、`acp-docker-min`、`config-minimal`、`sdk-agent-session`、`hard-ceiling-min`、`nooa-host-min` |
| `examples/journeys` | `terminal-jsonl-agg`、`env-postgres-min` |
| docker topology 示例 | `sdk-session-single-actor` lock；`multi-agent-*` lock 有 topology 即可（本轮不承诺多 group 真调度 run） |
| `examples/tau3-airline` | `airline-00` lock |

docker / e2b / ssh job 文档：`examples/core/profiles.docker.yaml` 等。

不要把 gaia / tau3 全 suite、五条 ACP 全付费 invoke 当成「设计漏了」。产品禁止 `examples/agents/mock-default`。
