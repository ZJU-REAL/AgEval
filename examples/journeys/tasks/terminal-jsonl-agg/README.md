# terminal-jsonl-agg

v1 **terminal-bench / jsonl-aggregator** case class:

- Agent works in Attempt workspace (JSONL files + instruction only)
- Must write `aggregates.json` by **aggregating real records\_\*.jsonl** (not prompt-fed gold)
- Harness **explicitly** `Agent.session` → `invoke` → read workspace file → `publish_json`
- L1 path: filtered package mount hides `evaluation/`; clean evaluator compares to gold
- No `TerminalBenchAdapter`

## ACP (default)

| profile id    | `options.entry` | placement                                |
| ------------- | --------------- | ---------------------------------------- |
| `terminal-pi` | `pi`            | L1 `docker exec` target (assurance:l1)   |

Alternate profile switch via `parameters.models.default` / first profile in `bora.yaml`:
`terminal-opencode`, `terminal-grok`.

```bash
uv run bora run examples/journeys --task terminal-jsonl-agg
```

Requires `bora-attempt:l1` image with ACP entries baked in, host credentials for
the chosen entry, and Docker.

`BORA_L1_USE_SOLUTION=1` seeds `solution/*` into the Attempt workspace for L1
isolation smoke only — **not** the real Agent acceptance path for this journey.
