# terminal-jsonl-agg

v1 **terminal-bench / jsonl-aggregator** case class:

- Agent works in Attempt workspace (JSONL files + instruction only)
- Must write `aggregates.json` by **aggregating real records\_\*.jsonl** (not prompt-fed gold)
- L1 path: filtered package mount hides `evaluation/`; clean evaluator compares to gold
- No `TerminalBenchAdapter`

## ACP (default)

| profile id    | `options.entry` | placement                                |
| ------------- | --------------- | ---------------------------------------- |
| `terminal-pi` | `pi`            | L1 residual `docker exec` (assurance:l1) |

Alternate first-profile switches in `bora.yaml`: `terminal-opencode`, `terminal-grok`
(residual path uses the **first** profile entry).

```bash
uv run bora run examples/journeys/terminal-jsonl-agg --task terminal-jsonl-agg
```

Requires `bora-attempt:l1` image with ACP entries baked in, host credentials for
the chosen entry, and Docker.

`BORA_L1_USE_SOLUTION=1` is for L1 isolation smoke only — **not** the real Agent
acceptance path for this journey.
