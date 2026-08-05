# env-postgres-min

Minimal Environment Manager + package seed + package-local DB tool smoke.

No Agent on the default path — validates Core env handoff and package `lib/` tools
before agent-backed journeys (`multiagent-env-min`, …).

## Package layout

| Path | Role |
| --- | --- |
| `harness.py` | Orchestration only (load env handoff → call tool → publish) |
| `evaluator.py` | Independent PASS |
| `lib/db_tools.py` | `db_query` ToolSet + env meta load |
| `environment/seed.sql` | Package seed applied by Core (generic, no task hardcode) |

Non-orchestration functional code lives under **`lib/`**.

```bash
uv run bora lock examples/journeys --task env-postgres-min
uv run bora run  examples/journeys --task env-postgres-min
```

Requires Docker for Attempt-local PostgreSQL. No ACP binary needed on this path.
