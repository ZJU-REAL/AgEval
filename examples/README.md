# ageval examples

Tracked **Datasets** (suites) for public smokes, case-class journeys, and
selected popular-bench **conversion** packages.

```text
examples/
├── agents/         # ageval.agent/1 examples (cc-default / pi-default / grok-jsonl-agg / http-default)
├── core/           # dataset example/core — Core surface gates
├── journeys/       # dataset example/journeys — case-class fidelity
├── l1/             # dataset example/l1 — docker topology packages
└── tau3-airline/   # dataset my-lab/tau3-airline — τ³-bench airline port
```

There is no product `executor: mock`. Offline lock uses the real kinds; a missing
credential fails closed. Bind a real Agent with `--agent` or `--profiles`.

Each top-level directory is one dataset (`ageval.dataset/1`). Members live under
`tasks/<task_id>/task.yaml`. CLI path is always the dataset root:

```bash
uv run ageval lock  examples/<database> --task <task_id>
uv run ageval run   examples/<database> --task <task_id>
uv run ageval tasks examples/<database>
```

## Suite run (Spec 22)

```bash
# Full dataset suite (no --task); concurrency from CLI or dataset defaults
uv run ageval run tests/fixtures/databases/suite-min --max-concurrent-tasks 2
# Single member still first-class
uv run ageval run examples/core --task config-minimal
```

## Frozen smoke commands (Spec 20)

```bash
uv run ageval lock examples/core --task config-minimal
uv run ageval lock examples/journeys --task terminal-jsonl-agg
uv run ageval lock examples/l1 --task sdk-session-single-actor
uv run ageval lock examples/tau3-airline --task airline-00   # conversion package; needs tau2 pin for run

uv run ageval run examples/core --task sdk-agent-session   # real agent path when credentials available
uv run ageval tasks examples/journeys

# Expected failures
uv run ageval lock examples/journeys --task does-not-exist   # exit ≠ 0
uv run ageval lock examples/core                            # missing --task → exit ≠ 0
uv run ageval lock examples/core --task config-invalid       # exit 2, unknown_profile
```

## `journeys/` (`dataset_id: example/journeys`)

| Task                                                       | Case class                        |
| ---------------------------------------------------------- | --------------------------------- |
| [`env-postgres-min`](journeys/tasks/env-postgres-min/)     | Environment + DB tools (no agent) |
| [`multiagent-env-min`](journeys/tasks/multiagent-env-min/) | Multi-session + SQL tools         |
| [`tau2-dialog-min`](journeys/tasks/tau2-dialog-min/)       | Dual-role dialog + tools          |
| [`terminal-jsonl-agg`](journeys/tasks/terminal-jsonl-agg/) | workspace file + clean eval    |

### External nooa plugin (optional profiles)

NVIDIA [OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents) path: real LiteLLM
calls via profile `model` / `base_url` / `api_key` (env locator). Install never
rewrites dataset profiles — bind with a separate profiles file:

```bash
uv sync --extra nooa
uv run ageval plugin install plugins/nooa
# repo/.env: litellm_api_key (+ litellm_base_url) or set profile base_url
unset AGEVAL_OFFLINE_AGENT
uv run ageval run examples/journeys --profiles examples/journeys/profiles.nooa.yaml
```

Package agents under each task’s `lib/agents.py` are `nooa.Agent` subclasses
(generation methods). Invoke runs the in-box worker through `host.exec` and
projects locators into that exec env. Docker bake installs `nooa` so the box
Python can import it.

### External dsh plugin (optional profiles)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) path: official
JSON-RPC SDK (`deepseek-harness-sdk`), not ACP. Same journeys harness; bind
`executor: dsh` + `extensions: [{plugin: dsh}]` + `model` + locator
`deepseek_api_key`. Invoke runs the in-box worker through `host.exec`. Docker
bake installs the wheels in the Attempt image — `--extra dsh` is for the local
kind's interpreter. `executor:` alone does not bake.

```bash
uv run ageval plugin install plugins/dsh
# repo/.env: deepseek_api_key (projected as DEEPSEEK_API_KEY)
unset AGEVAL_OFFLINE_AGENT
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
# Optional DSH file-effect policy (omit permission to keep unrestricted local tools):
# uv run ageval run examples/journeys --task terminal-jsonl-agg \
#   --profiles examples/journeys/profiles.dsh.read-only.yaml
```

## `slot-probe/` (`dataset_id: example/slot-probe`)

Multi-slot extension e2e (not a default public smoke). Requires:

```bash
uv run ageval plugin install plugins/nooa
uv run ageval plugin install plugins/slot-probe
uv run ageval run examples/slot-probe --task l0-env-agent
```

See [`slot-probe/README.md`](slot-probe/README.md).

## `core/` (`dataset_id: example/core`)

| Task                                                                       | Role                                    |
| -------------------------------------------------------------------------- | --------------------------------------- |
| [`config-minimal`](core/tasks/config-minimal/)                             | `ageval lock` success                     |
| [`config-invalid`](core/tasks/config-invalid/)                             | `ageval lock` expected-failure            |
| [`harness-minimal`](core/tasks/harness-minimal/)                           | Worker harness, no agent                |
| [`evaluator-negative`](core/tasks/evaluator-negative/)                     | completed ≠ PASS                        |
| [`sdk-agent-session`](core/tasks/sdk-agent-session/)                       | multi-invoke Agent + PASS            |
| [`plugin-agent-executor`](core/tasks/plugin-agent-executor/)               | `openai-http` second mechanism          |
| [`attempt-trajectory`](core/tasks/attempt-trajectory/)                     | §8.9 trajectory + `Result.logs`         |
| [`hard-ceiling-trajectory`](core/tasks/hard-ceiling-trajectory/)           | N+1 invoke denied                       |
| [`builtin-executor-conformance`](core/tasks/builtin-executor-conformance/) | Five ACP profiles (profile-only switch) |
| [`builtin-executor-mixed`](core/tasks/builtin-executor-mixed/)             | Dual profile independent trajectories   |
| [`sdk-tool-guard`](core/tasks/sdk-tool-guard/)                             | ToolSet success                         |
| [`sdk-tool-guard-denied`](core/tasks/sdk-tool-guard-denied/)               | Tool policy denial                      |
| [`environment-action-denied`](core/tasks/environment-action-denied/)       | Env undeclared/dangerous action deny    |

## docker topology 示例 (`dataset_id: example/l1`)

| Task                                                                           | Role                                    |
| ------------------------------------------------------------------------------ | --------------------------------------- |
| [`sdk-session-single-actor`](l1/tasks/sdk-session-single-actor/)               | SDK session in a container              |
| [`executor-image-official`](l1/tasks/executor-image-official/)                 | Dockerfile `FROM ageval-attempt:base`   |
| [`executor-image-upstream`](l1/tasks/executor-image-upstream/)                 | Upstream base + install-executors       |
| [`multi-agent-shared-container`](l1/tasks/multi-agent-shared-container/)       | shared-container multi-UID              |
| [`multi-agent-container-per-group`](l1/tasks/multi-agent-container-per-group/) | container-per-group                     |

Isolation (hidden gold, harness without credentials, writer-stop) is covered by
**Provider tests**: `tests/provider_l1/test_harness_isolation_contracts.py`,
`tests/provider_l1/test_filtered_mount.py` — not public probe packages.

## `tau3-airline/` (`dataset_id: my-lab/tau3-airline`)

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
uv run ageval lock examples/tau3-airline --task airline-00
uv run ageval tasks examples/tau3-airline
uv run python scripts/check_shared_lib_collisions.py examples/tau3-airline
# Full suite (long; needs agent credentials + tau2):
# uv run ageval run examples/tau3-airline
```

Package-local detail: [`tau3-airline/README.md`](tau3-airline/README.md). Regenerate members
from upstream tasks JSON: `python examples/tau3-airline/scripts/generate_package.py --all`.

## Hub-only conversions

Only **`tau3-airline`** lands in this monorepo. Larger popular-bench ports stay **out of
`examples/`** and ship as **Hub packages** (publish + suite upload), so clone size and CI
paths stay bounded:

| Upstream | Hub package id (org `my-lab`) | Notes |
| --- | --- | --- |
| Terminal-Bench 2.0 | `terminal-bench-2` / light `terminal-bench-2-10` | Docker + Harbor pytest-style verifier |
| MARBLE coding | `marble-coding` / light `marble-coding-10` | shared-container multi-agent coding |

Package presence, Hub publish, or a suite job on the board does **not** raise evidence grade
(`package ≠ real-benchmark-verified`).

> **Agent scheduling:** non-empty `agent_profiles` ⇒ Parent Agent Service / SDK
> session; harness owns every `Agent.session` / `invoke`. No Runtime one-shot.

## What was removed

| Former package                                                    | Reason                                                 |
| ----------------------------------------------------------------- | ------------------------------------------------------ |
| `core/agent-eval`                                                 | `sdk-agent-session`                                    |
| `core/acp-agent-conformance`                                      | `builtin-executor-conformance`                         |
| `core/orchestration-environment`                                  | `journeys/multiagent-env-min`                          |
| `l1/provider-l1-agent-eval`                                       | `sdk-session-single-actor`                             |
| `l1/builtin-executor-visibility` (+ denied)                       | single-actor + provider_l1 tests                       |
| `l1/acp-agent-placement`                                          | SDK session packages                                   |
| `l1/provider-l1-denied` / `projection-denied` / `residual-writer` | Application probe paths removed → `tests/provider_l1/` |
| `echo-contract` / `workspace-file-eval`                           | Earlier redundancy                                     |

## Suggested first runs

```bash
uv run ageval lock examples/core --task config-minimal
uv run ageval lock examples/core --task config-invalid   # expect exit 2
uv run ageval run examples/core --task sdk-agent-session
uv run pytest tests/provider_l1/test_harness_isolation_contracts.py -q
```
