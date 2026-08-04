# tau2-dialog-min

v1 **tau2-bench retail** case class on BORA v2 package surfaces.

## Package layout

| Path | Role |
| --- | --- |
| `harness.py` | Orchestration only (user sim → service agent loop → order gate → publish) |
| `evaluator.py` | Independent PASS vs gold |
| `lib/retail_tools.py` | Domain tools + state helpers (`find_customer` / `get_order` / …) |
| `lib/agent_json.py` | Invoke → JSON parse helpers |
| `data/` | Agent-facing initial state + private user-instructions |
| `evaluation/` | Evaluator-only gold (not mounted to agent) |

Non-orchestration functional code (Tool bodies, workflow allow prefix, JSON loaders)
lives under **`lib/`** — not in the harness entrypoint.

```bash
uv run bora lock examples/journeys/tau2-dialog-min --task tau2-dialog-min
uv run bora run examples/journeys/tau2-dialog-min --task tau2-dialog-min
```
