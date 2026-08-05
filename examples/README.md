# BORA examples

Tracked **Databases** (suites) for public smokes and case-class journeys.

```text
examples/
├── core/       # Database example/core — Core surface gates
├── journeys/   # Database example/journeys — case-class fidelity
└── l1/         # Database example/l1 — Provider L1
```

Each top-level directory is one Database (`bora.database/1`). Members live under
`tasks/<task_id>/task.yaml`. CLI path is always the Database root:

```bash
uv run bora lock  examples/<database> --task <task_id>
uv run bora run   examples/<database> --task <task_id>
uv run bora tasks examples/<database>
```

## Suite run (Spec 22)

```bash
# Full Database suite (no --task); concurrency from CLI or Database defaults
uv run bora run tests/fixtures/databases/suite-min --max-concurrent-tasks 2
# Single member still first-class
uv run bora run examples/core --task config-minimal
```

## Frozen smoke commands (Spec 20)

```bash
uv run bora lock examples/core --task config-minimal
uv run bora lock examples/journeys --task terminal-jsonl-agg
uv run bora lock examples/l1 --task sdk-session-single-actor

uv run bora run examples/core --task sdk-agent-session   # real agent path when credentials available
uv run bora tasks examples/journeys

# Expected failures
uv run bora lock examples/journeys --task does-not-exist   # exit ≠ 0
uv run bora lock examples/core                            # missing --task → exit ≠ 0
uv run bora lock examples/core --task config-invalid       # exit 2, unknown_profile
```

## `journeys/` (`database_id: example/journeys`)

| Task | Case class |
| --- | --- |
| [`env-postgres-min`](journeys/tasks/env-postgres-min/) | Environment + DB tools (no agent) |
| [`multiagent-env-min`](journeys/tasks/multiagent-env-min/) | Multi-session + SQL tools |
| [`tau2-dialog-min`](journeys/tasks/tau2-dialog-min/) | Dual-role dialog + tools |
| [`terminal-jsonl-agg`](journeys/tasks/terminal-jsonl-agg/) | L1 workspace file + clean eval |

## `core/` (`database_id: example/core`)

| Task | Role |
| --- | --- |
| [`config-minimal`](core/tasks/config-minimal/) | `bora lock` success |
| [`config-invalid`](core/tasks/config-invalid/) | `bora lock` expected-failure |
| [`harness-minimal`](core/tasks/harness-minimal/) | Worker harness, no agent |
| [`evaluator-negative`](core/tasks/evaluator-negative/) | completed ≠ PASS |
| [`sdk-agent-session`](core/tasks/sdk-agent-session/) | L0 multi-invoke Agent + PASS |
| [`plugin-agent-executor`](core/tasks/plugin-agent-executor/) | `openai-http` second mechanism |
| [`attempt-trajectory`](core/tasks/attempt-trajectory/) | §8.9 trajectory + `Result.logs` |
| [`hard-ceiling-trajectory`](core/tasks/hard-ceiling-trajectory/) | N+1 invoke denied |
| [`builtin-executor-conformance`](core/tasks/builtin-executor-conformance/) | Five ACP profiles (profile-only switch) |
| [`builtin-executor-mixed`](core/tasks/builtin-executor-mixed/) | Dual profile independent trajectories |
| [`sdk-tool-guard`](core/tasks/sdk-tool-guard/) | ToolSet success |
| [`sdk-tool-guard-denied`](core/tasks/sdk-tool-guard-denied/) | Tool policy denial |
| [`environment-action-denied`](core/tasks/environment-action-denied/) | Env undeclared/dangerous action deny |

## `l1/` (`database_id: example/l1`)

| Task | Role |
| --- | --- |
| [`sdk-session-single-actor`](l1/tasks/sdk-session-single-actor/) | L1 SDK session → attempt-container PASS |
| [`executor-image-official`](l1/tasks/executor-image-official/) | Dockerfile `FROM bora-attempt:l1` |
| [`executor-image-upstream`](l1/tasks/executor-image-upstream/) | Upstream base + install-executors |
| [`multi-agent-shared-container`](l1/tasks/multi-agent-shared-container/) | shared-container multi-UID |
| [`multi-agent-container-per-group`](l1/tasks/multi-agent-container-per-group/) | container-per-group |

Isolation (hidden gold, harness without credentials, writer-stop) is covered by
**Provider tests**: `tests/provider_l1/test_harness_isolation_contracts.py`,
`tests/provider_l1/test_filtered_mount.py` — not public probe packages.

> **Agent scheduling:** non-empty `agent_profiles` ⇒ Parent Agent Service / L1 SDK
> session; harness owns every `Agent.session` / `invoke`. No Runtime one-shot.

## What was removed

| Former package | Reason |
| --- | --- |
| `core/agent-eval` | `sdk-agent-session` |
| `core/acp-agent-conformance` | `builtin-executor-conformance` |
| `core/orchestration-environment` | `journeys/multiagent-env-min` |
| `l1/provider-l1-agent-eval` | `sdk-session-single-actor` |
| `l1/builtin-executor-visibility` (+ denied) | single-actor + provider_l1 tests |
| `l1/acp-agent-placement` | L1 SDK session packages |
| `l1/provider-l1-denied` / `projection-denied` / `residual-writer` | Application probe paths removed → `tests/provider_l1/` |
| `echo-contract` / `workspace-file-eval` | Earlier redundancy |

## Suggested first runs

```bash
uv run bora lock examples/core --task config-minimal
uv run bora lock examples/core --task config-invalid   # expect exit 2
uv run bora run examples/core --task sdk-agent-session
uv run pytest tests/provider_l1/test_harness_isolation_contracts.py -q
```
