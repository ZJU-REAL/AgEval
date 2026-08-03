# env-postgres-min

Minimal Environment Manager + package seed + package-local DB tool smoke.

No Agent on the default path — validates Core env handoff and package `lib/` tools.

## Package layout

| Path | Role |
| --- | --- |
| `harness.py` | Orchestration only (load env handoff → call tool → publish) |
| `evaluator.py` | Independent PASS |
| `lib/db_tools.py` | `db_query` ToolSet + env meta load |
| `environment/seed.sql` | Package seed applied by Core (generic, no task hardcode) |

Non-orchestration functional code lives under **`lib/`**.

```bash
uv run bora lock examples/journeys/env-postgres-min --task env-postgres-min
uv run bora run examples/journeys/env-postgres-min --task env-postgres-min
```
