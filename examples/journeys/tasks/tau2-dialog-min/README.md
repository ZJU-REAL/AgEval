# tau2-dialog-min

v1 **tau2-bench retail** case class on ageval v2 package surfaces.

## Package layout

| Path                  | Role                                                                      |
| --------------------- | ------------------------------------------------------------------------- |
| `run.py`              | Orchestration only (user sim → service agent loop → order gate → publish) |
| `evaluator.py`        | Independent PASS vs gold                                                  |
| `lib/retail_tools.py` | Domain tools + state helpers (`find_customer` / `get_order` / …)          |
| `lib/agent_json.py`   | Invoke → JSON parse helpers                                               |
| `data/`               | Agent-facing initial state + private user-instructions                    |
| `evaluation/`         | Evaluator-only gold (not mounted to agent)                                |

## ACP mix (default)

| Role           | profile id         | ACP `entry`     |
| -------------- | ------------------ | --------------- |
| user simulator | `user-grok`        | `grok-build`    |
| service agent  | `service-opencode` | `opencode`      |

(`user-pi` is listed as an alternate; some coding agents refuse retail roleplay —
the harness uses fixture-style generation prompts.)

Private customer facts stay in the user session only; the service agent sees the
customer message + tool observations, never the private instruction object.

Non-orchestration functional code (Tool bodies, workflow allow prefix, JSON loaders)
lives under **`lib/`** — not in the harness entrypoint.

```bash
uv run ageval lock examples/journeys --task tau2-dialog-min
uv run ageval run  examples/journeys --task tau2-dialog-min
```
