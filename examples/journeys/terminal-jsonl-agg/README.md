# terminal-jsonl-agg

v1 **terminal-bench / jsonl-aggregator** case class:

- Agent works in Attempt workspace (JSONL files + instruction only)
- Must write `aggregates.json` by **aggregating real records_*.jsonl** (not prompt-fed gold)
- L1 path: filtered package mount hides `evaluation/`; clean evaluator compares to gold
- No `TerminalBenchAdapter`

```bash
uv run bora run examples/journeys/terminal-jsonl-agg --task terminal-jsonl-agg
```

`BORA_L1_USE_SOLUTION=1` is for L1 isolation smoke only — not the real Agent acceptance path.
