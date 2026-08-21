# ageval examples

Tracked **datasets** for public smokes, case-class journeys, catalog Agents, and
one popular-bench conversion.

```text
examples/
├── agents/         # ageval.agent/1 (cc/pi/codex/opencode/dsh/nooa/miniswe)
├── journeys/       # dataset example/journeys — case-class fidelity
└── tau3-airline/   # dataset my-lab/tau3-airline — τ³-bench airline port
```

There is no product `executor: mock`. Offline lock uses the real kinds; a missing
credential fails closed. Bind a real Agent with `--agent` or `--profiles`.

CLI path is always the dataset root (`ageval.yaml`):

```bash
uv run ageval lock  examples/<dataset> --task <task_id>
uv run ageval run   examples/<dataset> --task <task_id>
uv run ageval tasks examples/<dataset>
```

## Suite

```bash
# Full dataset (omit --task); concurrency from CLI or dataset defaults
uv run ageval run examples/journeys --max-concurrent-tasks 2
uv run ageval run examples/journeys --task terminal-jsonl-agg
```

## Smoke

Default journeys profiles use `environment: docker`. `--probe` is lock + preflight
only.

```bash
uv run ageval lock examples/journeys --task terminal-jsonl-agg
uv run ageval lock examples/tau3-airline --task airline-00   # conversion; tau2 pin for run
uv run ageval run examples/journeys --task terminal-jsonl-agg
uv run ageval tasks examples/journeys

# Expected failures
uv run ageval lock examples/journeys --task does-not-exist   # exit ≠ 0
```

## `journeys/` (`dataset_id: example/journeys`)

| Task                                                       | Case class                        |
| ---------------------------------------------------------- | --------------------------------- |
| [`multiagent-env-min`](journeys/tasks/multiagent-env-min/) | Multi-session + SQL tools         |
| [`tau2-dialog-min`](journeys/tasks/tau2-dialog-min/)       | Dual-role dialog + tools          |
| [`terminal-jsonl-agg`](journeys/tasks/terminal-jsonl-agg/) | workspace file + clean eval       |

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
(generation methods). Invoke runs the in-environment worker through `host.exec` and
projects locators into that exec env. Docker bake installs `nooa` so the box
Python can import it.

### External dsh plugin (optional profiles)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) path: official
JSON-RPC SDK (`deepseek-harness-sdk`), not ACP. Same journeys `run.py`; bind
`executor: dsh` + `extensions: [{plugin: dsh}]` + `model` + locator
`deepseek_api_key`. Invoke runs the in-environment worker through `host.exec`. Docker
bake installs the wheels in the Attempt image — `--extra dsh` is for the local
kind's interpreter. `executor:` alone does not bake.

```bash
uv run ageval plugin install plugins/dsh
# repo/.env: deepseek_api_key (projected as DEEPSEEK_API_KEY)
unset AGEVAL_OFFLINE_AGENT
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
```

This journey writes `aggregates.json`, so omit `options.permission` or use
`workspace-write`. `read-only` fences DSH file-tool writes only; bash can still
write on the bundled jsonrpc runtime. That is not ageval isolation.

### Other environment kinds

```bash
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.e2b-acp.yaml --probe
# ssh A has dsh / nooa profiles; live ACP stdio over ssh A is unsupported
```

## `tau3-airline/` (`dataset_id: my-lab/tau3-airline`)

Popular-bench **port** of [tau2-bench](https://github.com/sierra-research/tau2-bench)
`airline` (τ³-bench) as **one domain = one dataset**. Dual-role dialog
(`user` + `service` via `profiles.yaml` → ACP `grok-build`) with package-local tools/DB
bridge and independent evaluator (tau2 ENV+COMMUNICATE). Default environment is `local`.

| Item         | Notes                                                                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Upstream pin | `tau2-bench` @ `v1.0.1` (`fc0055dc…`); paper [2506.07982](https://arxiv.org/abs/2506.07982)                                            |
| Members      | **50** tasks: `airline-00` … `airline-49` (upstream ids `0`…`49`)                                                                      |
| Layout       | Dataset-level [`shared/lib`](tau3-airline/shared/lib/) + [`shared/assets`](tau3-airline/shared/assets/); **no** per-task `lib/` copies |
| Gold         | Under each `tasks/airline-NN/evaluation/` only — not under `shared/`                                                                   |
| Host deps    | `tau2==1.0.1` (see [`tau3-airline/requirements.txt`](tau3-airline/requirements.txt)) for run/eval                                      |
| Evidence     | **Not** a public smoke upgrade path; package / Hub publish **≠** `real-benchmark-verified`                                             |

```bash
uv run ageval lock examples/tau3-airline --task airline-00
uv run ageval tasks examples/tau3-airline
uv run python scripts/check_shared_lib_collisions.py examples/tau3-airline
# Full suite (long; needs agent credentials + tau2):
# uv run ageval run examples/tau3-airline
```

Package-local detail: [`tau3-airline/README.md`](tau3-airline/README.md). Regenerate members
from upstream tasks JSON: `python examples/tau3-airline/scripts/generate_package.py --all`.

## `agents/` (`ageval.agent/1`)

Catalog Agent packages. Install into the local cache, then bind with `--agent`
(mutually exclusive with `--profiles`):

```bash
uv run ageval agent install examples/agents/pi-default
uv run ageval run examples/journeys --task terminal-jsonl-agg --agent pi-default
```

## Hub-only conversions

Only **`tau3-airline`** lands in this monorepo. Larger popular-bench ports stay **out of
`examples/`** and ship as **Hub packages** (publish + suite upload), so clone size and CI
paths stay bounded:

| Upstream           | Hub package id (org `my-lab`)                    | Notes                                 |
| ------------------ | ------------------------------------------------ | ------------------------------------- |
| Terminal-Bench 2.0 | `terminal-bench-2` / light `terminal-bench-2-10` | Docker + Harbor pytest-style verifier |
| MARBLE coding      | `marble-coding` / light `marble-coding-10`       | shared-container multi-agent coding   |

Package presence, Hub publish, or a suite job on the board does **not** raise evidence grade
(`package ≠ real-benchmark-verified`).

## Suggested first runs

```bash
uv run ageval lock examples/journeys --task terminal-jsonl-agg
uv run ageval run examples/journeys --task terminal-jsonl-agg
uv run ageval lock examples/tau3-airline --task airline-00
```
