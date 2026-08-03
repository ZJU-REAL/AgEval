# orchestration-environment

Core surface combo: **multi-profile Agent + Attempt-local PostgreSQL + package tools**.

Orchestration-only harness:

1. Short invoke on a second profile (`codex-reviewer`) — multi-profile boundary
2. Specialist SQL via package `lib/` `db_query` tools against seeded env
3. Planner / reducer style multi-invoke on `codex-mini`
4. Publish reducer output; independent evaluator scores labels vs sealed gold

Closer to a journey than thin config smokes, but still a **Core gate** (not a
full case-class demo — see `examples/journeys/multiagent-env-min` for product shape).

## Package layout

| Path | Role |
| --- | --- |
| `harness.py` | Orchestration only |
| `evaluator.py` | Independent PASS vs gold |
| `lib/` | DB tools, diagnostics SQL, JSON helpers |
| `environment/seed.sql` | Generic package seed |
| `evaluation/expected.json` | Evaluator-only gold |

## Requirements

- Codex for both profiles
- Docker / env manager for PostgreSQL

## Run

```bash
uv run bora lock examples/core/orchestration-environment --task orchestration-environment
uv run bora run  examples/core/orchestration-environment --task orchestration-environment
```
