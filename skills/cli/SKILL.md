---
name: bora-cli
description: How to run BORA public CLI (lock / run / campaign / evidence) for coding agents.
---

# BORA CLI

Install (repo root):

```bash
uv sync --frozen --all-packages
uv run bora --help
```

## Commands (shipped)

| Command | Purpose |
| --- | --- |
| `bora lock <package> --task <id>` | Config Core lock summary (no Agent) |
| `bora run <package> --task <id>` | Foreground Attempt |
| `bora run ... --set /parameters/active_profile="pi-mini"` | Profile override (allowlisted) |
| `bora campaign ...` | Serial matrix (partial) |
| `bora evidence <logs-path> --out <dir>` | Trajectory export (re-redacted) |
| `bora status <run_id>` | Control store query |

## Success smoke examples

```bash
uv run bora lock examples/core/config-minimal --task config-minimal
uv run bora run examples/core/attempt-trajectory --task attempt-trajectory
uv run bora run examples/core/builtin-executor-conformance --task builtin-executor-conformance \
  --set '/parameters/active_profile="codex-mini"'
```

## Exit codes

- `0` PASS
- `1` FAIL (evaluator)
- `2` ERROR / config / runtime

## Antipatterns

- Do not treat stdout prose as trajectory truth — use `Result.logs` evidence tree.
- Do not pass secrets on CLI flags.
- Offline: `BORA_OFFLINE_AGENT=1` must never produce PASS on agent packages.

Design: `docs/design/05-runtime-core.md`
