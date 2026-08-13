# BORA examples

Tracked **Databases** (suites) for public smokes, case-class journeys, and
selected popular-bench **conversion** packages.

```text
examples/
├── core/           # Database example/core — Core surface gates
├── journeys/       # Database example/journeys — case-class fidelity
├── l1/             # Database example/l1 — Provider L1
├── slot-probe/     # multi-slot plugin e2e (install plugins first)
└── tau3-airline/   # Database my-lab/tau3-airline — τ³-bench airline port
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
uv run bora lock examples/tau3-airline --task airline-00   # conversion package; needs tau2 pin for run

uv run bora run examples/core --task sdk-agent-session   # real agent path when credentials available
uv run bora tasks examples/journeys

# Expected failures
uv run bora lock examples/journeys --task does-not-exist   # exit ≠ 0
uv run bora lock examples/core                            # missing --task → exit ≠ 0
uv run bora lock examples/core --task config-invalid       # exit 2, unknown_profile
```

## `journeys/` (`database_id: example/journeys`)

| Task                                                       | Case class                        |
| ---------------------------------------------------------- | --------------------------------- |
| [`env-postgres-min`](journeys/tasks/env-postgres-min/)     | Environment + DB tools (no agent) |
| [`multiagent-env-min`](journeys/tasks/multiagent-env-min/) | Multi-session + SQL tools         |
| [`tau2-dialog-min`](journeys/tasks/tau2-dialog-min/)       | Dual-role dialog + tools          |
| [`terminal-jsonl-agg`](journeys/tasks/terminal-jsonl-agg/) | L1 workspace file + clean eval    |

### External nooa plugin (optional profiles)

NVIDIA [OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents) path: real LiteLLM
calls via profile `model` / `base_url` / `api_key` (env locator). Install never
rewrites Database profiles — bind with a separate profiles file:

```bash
uv sync --extra nooa
uv run bora plugin install plugins/nooa
# repo/.env: litellm_api_key (+ litellm_base_url) or set profile base_url
unset BORA_OFFLINE_AGENT
uv run bora run examples/journeys --profiles examples/journeys/profiles.nooa.yaml
```

Package agents under each task’s `lib/agents.py` are `nooa.Agent` subclasses
(generation methods). L1 Ready bakes `nooa` + in-container worker and projects
credentials — not parent host SPI success.

### External dsh plugin (optional profiles)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) path: official
JSON-RPC SDK (`deepseek-harness-sdk`), not ACP. Same journeys harness; bind
`executor: dsh` + `model` + locator `deepseek_api_key`. L1 bake installs the
wheels in the Attempt image — host `--extra dsh` is only for L0 host SPI.

```bash
uv run bora plugin install plugins/dsh
# repo/.env: deepseek_api_key (projected as DEEPSEEK_API_KEY)
unset BORA_OFFLINE_AGENT
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
# Optional DSH file-effect policy (omit permission to keep unrestricted local tools):
# uv run bora run examples/journeys --task terminal-jsonl-agg \
#   --profiles examples/journeys/profiles.dsh.read-only.yaml
```

## `slot-probe/` (`database_id: example/slot-probe`)

Multi-slot extension e2e (not a default public smoke). Requires:

```bash
uv run bora plugin install plugins/nooa
uv run bora plugin install plugins/slot-probe
uv run bora run examples/slot-probe --task l0-env-agent
```

See [`slot-probe/README.md`](slot-probe/README.md).

## `core/` (`database_id: example/core`)

| Task                                                                       | Role                                    |
| -------------------------------------------------------------------------- | --------------------------------------- |
| [`config-minimal`](core/tasks/config-minimal/)                             | `bora lock` success                     |
| [`config-invalid`](core/tasks/config-invalid/)                             | `bora lock` expected-failure            |
| [`harness-minimal`](core/tasks/harness-minimal/)                           | Worker harness, no agent                |
| [`evaluator-negative`](core/tasks/evaluator-negative/)                     | completed ≠ PASS                        |
| [`sdk-agent-session`](core/tasks/sdk-agent-session/)                       | L0 multi-invoke Agent + PASS            |
| [`plugin-agent-executor`](core/tasks/plugin-agent-executor/)               | `openai-http` second mechanism          |
| [`attempt-trajectory`](core/tasks/attempt-trajectory/)                     | §8.9 trajectory + `Result.logs`         |
| [`hard-ceiling-trajectory`](core/tasks/hard-ceiling-trajectory/)           | N+1 invoke denied                       |
| [`builtin-executor-conformance`](core/tasks/builtin-executor-conformance/) | Five ACP profiles (profile-only switch) |
| [`builtin-executor-mixed`](core/tasks/builtin-executor-mixed/)             | Dual profile independent trajectories   |
| [`sdk-tool-guard`](core/tasks/sdk-tool-guard/)                             | ToolSet success                         |
| [`sdk-tool-guard-denied`](core/tasks/sdk-tool-guard-denied/)               | Tool policy denial                      |
| [`environment-action-denied`](core/tasks/environment-action-denied/)       | Env undeclared/dangerous action deny    |

## `l1/` (`database_id: example/l1`)

| Task                                                                           | Role                                    |
| ------------------------------------------------------------------------------ | --------------------------------------- |
| [`sdk-session-single-actor`](l1/tasks/sdk-session-single-actor/)               | L1 SDK session → attempt-container PASS |
| [`executor-image-official`](l1/tasks/executor-image-official/)                 | Dockerfile `FROM bora-attempt:l1`       |
| [`executor-image-upstream`](l1/tasks/executor-image-upstream/)                 | Upstream base + install-executors       |
| [`multi-agent-shared-container`](l1/tasks/multi-agent-shared-container/)       | shared-container multi-UID              |
| [`multi-agent-container-per-group`](l1/tasks/multi-agent-container-per-group/) | container-per-group                     |

Isolation (hidden gold, harness without credentials, writer-stop) is covered by
**Provider tests**: `tests/provider_l1/test_harness_isolation_contracts.py`,
`tests/provider_l1/test_filtered_mount.py` — not public probe packages.

## `tau3-airline/` (`database_id: my-lab/tau3-airline`)

Popular-bench **port** of [tau2-bench](https://github.com/sierra-research/tau2-bench)
`airline` (τ³-bench) as **one domain = one Dataset**. Dual-role dialog
(`user` + `service` via `profiles.yaml` → ACP `grok-build`) with package-local tools/DB
bridge and independent evaluator (tau2 ENV+COMMUNICATE).

| Item         | Notes                                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Upstream pin | `tau2-bench` @ `v1.0.1` (`fc0055dc…`); paper [2506.07982](https://arxiv.org/abs/2506.07982)                                                  |
| Members      | **50** tasks: `airline-00` … `airline-49` (upstream ids `0`…`49`)                                                                            |
| Layout       | Dataset-level [`shared/lib`](tau3-airline/shared/lib/) + [`shared/assets`](tau3-airline/shared/assets/); **no** per-task `lib/` copies |
| Gold         | Under each `tasks/airline-NN/evaluation/` only — not under `shared/`                                                                         |
| Host deps    | `tau2==1.0.1` (see [`tau3-airline/requirements.txt`](tau3-airline/requirements.txt)) for run/eval                                            |
| Evidence     | **Not** a public smoke upgrade path; package / Hub publish **≠** `real-benchmark-verified`                                                   |

```bash
uv run bora lock examples/tau3-airline --task airline-00
uv run bora tasks examples/tau3-airline
uv run python scripts/check_shared_lib_collisions.py examples/tau3-airline
# Full suite (long; needs agent credentials + tau2):
# uv run bora run examples/tau3-airline
```

Package-local detail: [`tau3-airline/README.md`](tau3-airline/README.md). Regenerate members
from upstream tasks JSON: `python examples/tau3-airline/scripts/generate_package.py --all`.

## Hub-only conversions

Only **`tau3-airline`** lands in this monorepo. Larger popular-bench ports stay **out of
`examples/`** and ship as **Hub packages** (publish + suite upload), so clone size and CI
paths stay bounded:

| Upstream | Hub package id (org `my-lab`) | Notes |
| --- | --- | --- |
| Terminal-Bench 2.0 | `terminal-bench-2` / light `terminal-bench-2-10` | L1 Docker + Harbor pytest-style verifier |
| MARBLE coding | `marble-coding` / light `marble-coding-10` | L1 shared-container multi-agent coding |

Package presence, Hub publish, or a suite job on the board does **not** raise evidence grade
(`package ≠ real-benchmark-verified`).

> **Agent scheduling:** non-empty `agent_profiles` ⇒ Parent Agent Service / L1 SDK
> session; harness owns every `Agent.session` / `invoke`. No Runtime one-shot.

## What was removed

| Former package                                                    | Reason                                                 |
| ----------------------------------------------------------------- | ------------------------------------------------------ |
| `core/agent-eval`                                                 | `sdk-agent-session`                                    |
| `core/acp-agent-conformance`                                      | `builtin-executor-conformance`                         |
| `core/orchestration-environment`                                  | `journeys/multiagent-env-min`                          |
| `l1/provider-l1-agent-eval`                                       | `sdk-session-single-actor`                             |
| `l1/builtin-executor-visibility` (+ denied)                       | single-actor + provider_l1 tests                       |
| `l1/acp-agent-placement`                                          | L1 SDK session packages                                |
| `l1/provider-l1-denied` / `projection-denied` / `residual-writer` | Application probe paths removed → `tests/provider_l1/` |
| `echo-contract` / `workspace-file-eval`                           | Earlier redundancy                                     |

## Suggested first runs

```bash
uv run bora lock examples/core --task config-minimal
uv run bora lock examples/core --task config-invalid   # expect exit 2
uv run bora run examples/core --task sdk-agent-session
uv run pytest tests/provider_l1/test_harness_isolation_contracts.py -q
```
