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

Profiles: `terminal-pi` (default), `terminal-opencode`, `terminal-grok`.

```bash
uv run bora run examples/journeys --task terminal-jsonl-agg
# switch ACP entry via allowlisted override
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --set '/parameters/active_profile="terminal-opencode"'
```

Requires `bora-attempt:l1` image with ACP entries baked in, host credentials for
the chosen entry, and Docker.

## dsh plugin (optional)

Same harness; bind DeepSeek Harness via an alternate profiles file (not ACP):

```bash
uv run bora plugin install plugins/dsh
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
```

This journey writes `aggregates.json`, so omit `options.permission` or use
`workspace-write`. `read-only` is a DSH file-effect policy for jobs that
must not write; it is not BORA isolation.

```bash
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.read-only.yaml
# or: --set '/bindings/solver/options/permission="read-only"'
```

Needs locator `deepseek_api_key` in repo `.env`. L1 bake installs
`deepseek-harness-sdk` in the Attempt image.

`BORA_L1_USE_SOLUTION=1` seeds `solution/*` into the Attempt workspace for L1
isolation smoke only — **not** the real Agent acceptance path for this journey.
