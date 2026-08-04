# multiagent-env-min

v1 **multiagentbench / database-52** case class on BORA v2 Core surfaces.

| v1 oracle | v2 mapping |
| --- | --- |
| Multi specialist + planner + reducer | `AgentSession` multi-invoke (roles via prompts) |
| Environment diagnostic tools | `lib` `ToolSet.db_query` → Attempt-local PostgreSQL |
| Sealed reducer labels | Independent evaluator vs `evaluation/expected.json` |

**Not** a `MultiAgentBenchAdapter`. Gold labels are **not** in agent prompts; they
must be discovered from seeded DB rows via tools.

## Package layout

| Path | Role |
| --- | --- |
| `harness.py` | Orchestration only (specialist → planner → reducer loop) |
| `evaluator.py` | Independent PASS vs gold labels |
| `lib/db_tools.py` | `db_query` ToolSet + env handoff load |
| `lib/diagnostics.py` | Specialist SQL probes + allowed label set |
| `lib/agent_json.py` | Invoke → JSON parse helpers |
| `environment/seed.sql` | Generic package seed (Core runs as SQL statements) |
| `data/instruction.md` | Optional agent-visible brief |
| `evaluation/` | Evaluator-only gold |

Non-orchestration functional code lives under **`lib/`**.

```bash
uv run bora lock examples/journeys/multiagent-env-min --task multiagent-env-min
uv run bora run examples/journeys/multiagent-env-min --task multiagent-env-min
```
