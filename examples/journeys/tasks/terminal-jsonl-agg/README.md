# terminal-jsonl-agg

v1 **terminal-bench / jsonl-aggregator** case class:

- Agent works in Attempt workspace (JSONL files + instruction only)
- Must write `aggregates.json` by **aggregating real records\_\*.jsonl** (not prompt-fed gold)
- Harness **explicitly** `Agent.session` → `invoke` → read workspace file → `publish_json`
- L1 path: filtered package mount hides `evaluation/`; clean evaluator compares to gold
- No `TerminalBenchAdapter`

## ACP (default)

| profile id    | ACP `entry`     | placement                                |
| ------------- | --------------- | ---------------------------------------- |
| `terminal-pi` | `pi`            | L1 `docker exec` target (assurance:l1)   |

Profiles: Database `profiles.yaml` (default ACP mix), `acp-profiles/` overlays
(including `profiles.acp.grok-build.agent-skills.yaml` for grok-build plus a
shipped `jsonl-agg` skill).

```bash
uv run ageval run examples/journeys --task terminal-jsonl-agg
# switch ACP entry via allowlisted override
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --set '/parameters/active_profile="terminal-opencode"'
```

Requires `ageval-attempt:l1` image with ACP entries baked in, host credentials for
the chosen entry, and Docker.

## dsh plugin (optional)

Same harness; bind DeepSeek Harness via an alternate profiles file (not ACP):

```bash
uv run ageval plugin install plugins/dsh
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
```

This journey writes `aggregates.json`, so omit `options.permission` or use
`workspace-write`. `read-only` fences DSH file-tool writes only; bash can
still write on the bundled jsonrpc runtime. It is not ageval isolation.

```bash
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.read-only.yaml
# or: --set '/bindings/solver/options/permission="read-only"'
```

Needs locator `deepseek_api_key` in repo `.env`. L1 bake installs
`deepseek-harness-sdk` in the Attempt image.

`AGEVAL_L1_USE_SOLUTION=1` seeds `solution/*` into the Attempt workspace for L1
isolation smoke only — **not** the real Agent acceptance path for this journey.
