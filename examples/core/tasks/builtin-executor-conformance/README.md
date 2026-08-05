# builtin-executor-conformance

**Profile-only** multi-executor switch: same harness, different backends.

Package declares `codex`, `pi`, and `opencode` profiles. The harness never branches
on executor name — it only opens `session(active_profile)` from
`parameters.active_profile` (default `codex-mini`) and asks for JSON
`{"answer": 42}`.

## What you learn

- Adapters are selected by **profile / executor mechanism**, not by task name
- One harness works across builtin executors
- Switch backends with package params / `--set`, not code forks

## Requirements

- Credentials / CLIs for the profile you select (`codex-mini`, `pi-mini`, or
  `opencode-mini`)

## Run

```bash
# default profile (codex)
uv run bora run examples/core/builtin-executor-conformance --task builtin-executor-conformance

# other profiles (allowlisted --set, if enabled for this pointer)
# active_profile: pi-mini | opencode-mini
```
