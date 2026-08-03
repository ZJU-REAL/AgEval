# builtin-executor-mixed

**Same Attempt, two profiles**, independent sessions and trajectory trees.

Harness opens `codex-mini` then `pi-mini` in sequence (one invoke each). Both must
succeed with structured JSON. Proves multi-executor coexistence under one Attempt
identity without merging sessions.

## What you learn

- Multiple agent profiles in one package are first-class
- Sessions stay independent per profile
- Trajectory / invocation ids remain attributable per invoke

## Requirements

- Both Codex and Pi (or configured executors) available

## Run

```bash
uv run bora lock examples/core/builtin-executor-mixed --task builtin-executor-mixed
uv run bora run  examples/core/builtin-executor-mixed --task builtin-executor-mixed
```
