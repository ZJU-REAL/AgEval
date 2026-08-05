# BORA examples

Tracked Task Packages for public smokes and case-class journeys.

```text
examples/
├── journeys/   # case-class fidelity
├── core/       # Core surface gates
└── l1/         # Provider L1 (SDK session + image paths)
```

```bash
uv run bora lock examples/<category>/<package> --task <task_id>
uv run bora run  examples/<category>/<package> --task <task_id>
```

## `journeys/`

| Package | Case class |
| --- | --- |
| [`env-postgres-min`](journeys/env-postgres-min/) | Environment + DB tools (no agent) |
| [`multiagent-env-min`](journeys/multiagent-env-min/) | Multi-session + SQL tools |
| [`tau2-dialog-min`](journeys/tau2-dialog-min/) | Dual-role dialog + tools |
| [`terminal-jsonl-agg`](journeys/terminal-jsonl-agg/) | L1 workspace file + clean eval |

## `core/`

| Package | Role |
| --- | --- |
| [`config-minimal`](core/config-minimal/) | `bora lock` success |
| [`config-invalid`](core/config-invalid/) | `bora lock` expected-failure |
| [`harness-minimal`](core/harness-minimal/) | Worker harness, no agent |
| [`evaluator-negative`](core/evaluator-negative/) | completed ≠ PASS |
| [`sdk-agent-session`](core/sdk-agent-session/) | L0 multi-invoke Agent + PASS |
| [`plugin-agent-executor`](core/plugin-agent-executor/) | `openai-http` second mechanism |
| [`attempt-trajectory`](core/attempt-trajectory/) | §8.9 trajectory + `Result.logs` |
| [`hard-ceiling-trajectory`](core/hard-ceiling-trajectory/) | N+1 invoke denied |
| [`builtin-executor-conformance`](core/builtin-executor-conformance/) | Five ACP profiles (profile-only switch) |
| [`builtin-executor-mixed`](core/builtin-executor-mixed/) | Dual profile independent trajectories |
| [`sdk-tool-guard`](core/sdk-tool-guard/) | ToolSet success |
| [`sdk-tool-guard-denied`](core/sdk-tool-guard-denied/) | Tool policy denial |
| [`environment-action-denied`](core/environment-action-denied/) | Env undeclared/dangerous action deny |

## `l1/`

| Package | Role |
| --- | --- |
| [`sdk-session-single-actor`](l1/sdk-session-single-actor/) | L1 SDK session → attempt-container PASS |
| [`executor-image-official`](l1/executor-image-official/) | Dockerfile `FROM bora-attempt:l1` |
| [`executor-image-upstream`](l1/executor-image-upstream/) | Upstream base + install-executors |
| [`multi-agent-shared-container`](l1/multi-agent-shared-container/) | shared-container multi-UID |
| [`multi-agent-container-per-group`](l1/multi-agent-container-per-group/) | container-per-group |

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
uv run bora lock examples/core/config-minimal --task config-minimal
uv run bora lock examples/core/config-invalid --task config-invalid   # expect exit 2
uv run bora run examples/core/sdk-agent-session --task sdk-agent-session
uv run pytest tests/provider_l1/test_harness_isolation_contracts.py -q
```
