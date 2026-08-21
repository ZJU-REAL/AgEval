# multiagent-env-min

v1 **multiagentbench / database-52** case class on ageval v2 Core surfaces.

| v1 oracle                            | v2 mapping                                                    |
| ------------------------------------ | ------------------------------------------------------------- |
| Multi specialist + planner + reducer | Independent `AgentSession`s (roles via prompts + profile ids) |
| Environment diagnostic tools         | `lib` `ToolSet.db_query` → Attempt-local PostgreSQL           |
| Sealed reducer labels                | Independent evaluator vs `evaluation/expected.json`           |
| Heterogeneous agent backends         | Mixed ACP entries in one Attempt                              |

**Not** a `MultiAgentBenchAdapter`. Gold labels are **not** in agent prompts; they
must be discovered from seeded DB rows via tools.

## ACP mix (default)

| Role                    | profile id         | ACP `entry`     |
| ----------------------- | ------------------ | --------------- |
| specialists (×5 probes) | `specialist-pi`    | `pi`            |
| planner                 | `planner-opencode` | `opencode`      |
| reducer                 | `reducer-grok`     | `grok-build`    |

Harness reads profile ids from `parameters.roles` — it never branches on entry name.

## Package layout

| Path                   | Role                                                |
| ---------------------- | --------------------------------------------------- |
| `harness.py`           | Orchestration only (specialist → planner → reducer) |
| `evaluator.py`         | Independent PASS vs gold labels                     |
| `lib/db_tools.py`      | `db_query` ToolSet + env handoff load               |
| `lib/diagnostics.py`   | Specialist SQL probes + allowed label set           |
| `lib/agent_json.py`    | Invoke → JSON parse helpers                         |
| `environment/seed.sql` | Generic package seed (Core runs as SQL statements)  |
| `data/instruction.md`  | Optional agent-visible brief                        |
| `evaluation/`          | Evaluator-only gold                                 |

```bash
uv run ageval lock examples/journeys --task multiagent-env-min
uv run ageval run  examples/journeys --task multiagent-env-min
```

Requires host ACP readiness for `pi`, `opencode`, and `grok-build` (`uv run ageval executors -v`),
plus Docker for the Attempt-local PostgreSQL environment.
