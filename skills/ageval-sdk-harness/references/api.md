# ageval_sdk public surface (shipped)

Package: `ageval_sdk` (see `sdk/python/src/ageval_sdk/`).

## Types

| Symbol | Role |
| --- | --- |
| `RunContext` | params, workspace, artifact_dir, agent, publish |
| `RunScope` | attempt/trial/run identity (parent-owned) |
| `Agent` | factory for sessions bound to attempt |
| `AgentSession` | `open` / `invoke` / `close` via parent socket |
| `Tool` / `ToolSet` | local tools |
| `AllowList` / `CallLimit` | soft local guards |
| `RunTerminal` | completed / failed — not PASS |
| `bounded_gather` / `collect_results` / `first_success` | workflow helpers |

## AgentSession.invoke return keys (parent path)

Includes `ok`, `error`, `text`, `structured`, `provider_session_handle`, `invocation_id`, `evidence_relative` when parent provides them.

## Offline

When `AGEVAL_OFFLINE_AGENT=1`, invoke fails closed (`offline_forced`) — never stub PASS on public paths.

Design: `docs/design/03-task-run-and-sdk.md`.
