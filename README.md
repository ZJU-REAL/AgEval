# ageval

**agent eval** — lock a dataset, pick an environment, run the task, let an independent evaluator own the score.

[中文](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/ageval?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/ageval/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

> Agent evaluation typically scores the **model**, while orchestration, isolation, visibility, and scoring authority remain inside each vendor harness. After changing the coding agent or the environment, scores are no longer comparable.
>
> **ageval** is the outer runtime that stays fixed when those parts change: lock a dataset, open one environment, execute the task `run.py`, and bind PASS only from an independent `evaluator.py`. Coding agents enter through **ACP**. Other backends are installed as plugins and bound from job profiles.

## Contents

- [What it is](#what-it-is)
- [How it works](#how-it-works)
- [Features](#features)
- [Getting started](#getting-started)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Docs](#docs)

## What it is

ageval is a **bounded evaluation runtime** for agents, not another agent.

- **The unit of delivery is a dataset**, not a full copy of a vendor suite. The root is `ageval.yaml`; members are `tasks/<id>/task.yaml`. CLI paths are always the dataset root.
- **An Attempt is visible.** Phases are environment → run → evaluate → record, with cleanup in `finally`. Opening `src/ageval/attempt/` shows the order.
- **The environment is a single slot:** `local` / `docker` / `e2b` / `ssh`. The Protocol is the same (`upload` / `exec` / `attach_stdio`). Change kind on `profiles.yaml`; `run.py` does not need to change.
- **Coding agents are real CLIs over ACP** (pi, Codex, Claude, OpenCode, Grok, and others). The parent process is the only JSON-RPC client.
- **Other backends are plugins** (`ageval.plugin/1`): nooa, dsh, miniswe. Install into the local cache, then bind from profiles. Install never rewrites the dataset.
- **PASS is not completion of the Agent.** `evaluator.py` runs after gold is uploaded. Trajectories are for inspection.

## How it works

```text
            you ── lock / run ──►  ┌─────────────────┐
                                   │     Attempt     │  lock dataset · digest
                                   │   ageval core   │  environment → run
                                   │                 │  evaluate → record
                                   │                 │  finally cleanup
                                   └────────┬────────┘
                                            │ opens one environment
              ┌─────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
        ┌───────────┐                 ┌───────────┐                 ┌───────────┐
        │   local   │                 │  docker   │                 │ e2b / ssh │
        └─────┬─────┘                 └─────┬─────┘                 └─────┬─────┘
              └──────── Protocol: upload · exec · attach_stdio ───────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │     run.py      │  task loop · Agent invoke
                                   │  ACP / plugin   │  executor slot
                                   └────────┬────────┘
                                            ▼
                                   ┌─────────────────┐
                                   │  evaluator.py   │  only source of PASS
                                   └─────────────────┘
```

1. **Lock the experiment.** `ageval lock` merges dataset, task, and profiles, checks capabilities, and writes a digest. Secrets remain locators; they are not stored as plaintext in the lock.
2. **Open one environment.** Kind comes from `environment:` on `profiles.yaml`. `--probe` performs lock and preflight only: missing `E2B_API_KEY` or SSH locators fail closed.
3. **Run the task, not the pipeline.** `run.py` owns the loop, tools, and Agent invocation. ACP takes `attach_stdio` from the environment; dsh / nooa / miniswe use `exec` / `upload`.
4. **Score independently.** Writers are stopped, gold (`evaluation/`) is uploaded, and `evaluator.py` binds PASS / FAIL / ERROR. Cleanup always runs.

Changing the environment or the Agent does not require changing the task `run.py`.

## Features

**Execution**

- **`ageval lock` / `run` / `campaign`.** A single task, a full dataset suite (omit `--task`), or a parameter matrix on one task. Always-k (`-k`) is a job axis, not a campaign axis.
- **ACP entries.** The same `run.py` with a different `options.entry` (pi / Codex / Claude / OpenCode / Grok). `--set` covers allowlisted pointers; `--profiles` replaces the entire job document.
- **Agent packages.** After installing `ageval.agent/1`, bind with `--agent` on lock / run / campaign. `--agent` and `--profiles` are mutually exclusive.
- **Plugins.** `ageval plugin install plugins/nooa` (or `dsh`, `miniswe`), then bind `executor:` and `extensions`. Docker bakes plugin layers from the plugin package.
- **`--probe`.** Prints plan and readiness for this binding and environment. No Agent invocation, no bake, no digest change.

**Environment**

- **Four kinds, one Protocol.** `local` directory, `docker` container, `e2b` sandbox, `ssh` remote host. ACP does not import docker, e2b, or ssh.
- **Gold is outside the Agent view.** `evaluation/` is not mounted; it is uploaded at evaluate.
- **Limits are enforced before invocation.** Wall time, memory, processes, and invocation ceilings are enforced by the runtime; `run.py` cannot raise them.
- **ssh A** does not support live ACP stdio; journeys ssh A profiles use dsh / nooa `exec`. Default CI does not treat live e2b / ssh Agent runs as verified.

**Inspect results**

- **`ageval view`.** Local Jobs → Tasks → Attempt. Reads `.ageval/suite-runs/` and `.ageval/runs/` under the opened dataset. Does not connect to Registry.
- **`ageval evidence`.** Exports a sealed trajectory copy without changing the score.
- **Hub + Registry.** Publish datasets, plugins, and Agent packages; upload suites. The public Leaderboard lists complete, release-bound suites only. Organization owners manage members, visibility, versions, and releases.

**Author tasks**

- **Dataset layout.** `ageval.yaml` + `profiles.yaml` + `tasks/<id>/{task.yaml,run.py,evaluator.py}`. Optional `environment/` and `shared/`.
- **`ageval_sdk`.** `RunContext`, `Agent.session`, tools, and terminals — optional. The SDK does not decide PASS and does not hold host credentials.
- **Mechanism plugins.** Exclusive slots (`environment`, `executor`, `evaluation_runtime`, `trajectory_seal`) and chain slots. Named by mechanism, not by benchmark.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and CPython **3.12+**. A live coding-agent run also requires a host ACP entry and credentials. `ageval lock` does not.

```bash
git clone https://github.com/ZJU-REAL/ageval.git
cd ageval
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/journeys
uv run ageval lock examples/journeys --task terminal-jsonl-agg
uv run ageval run  examples/journeys --task terminal-jsonl-agg
uv run ageval run  examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.e2b-acp.yaml --probe
uv run ageval executors -v
uv run ageval view examples/journeys --no-browser
```

Default `examples/journeys` profiles use `environment: docker`. Install an Agent package with `ageval agent install examples/agents/pi-default`, then bind it with `--agent`.

In-repo examples: [`examples/README.md`](examples/README.md) — journeys, `tau3-airline`, and catalog Agents.

## Architecture

```text
  ageval.yaml + task.yaml + profiles.yaml
                 │
                 ▼
           ageval lock                 digest · extension_bindings
                 │
                 ▼
           ageval run  ── Attempt ── environment → run → evaluate → record
                 │                      finally cleanup
                 ▼
        .ageval/runs/<id>/             lock.json · result.json · trajectory.jsonl
                 │
      ┌──────────┼──────────┐
      ▼                     ▼
 ageval view          Registry / Hub
 local Jobs           publish · upload-suite · Leaderboard
```

- **Config Core** is the only reader of dataset YAML. An unknown format yields a single `invalid_format` error.
- **Attempt** owns identity, deadlines, cleanup, and PASS binding. Plugins change lock-time bindings; they do not reorder the five phases.
- **CLI** talks only to `ageval.application.composition`. Hub is a Registry SPA; Viewer reads local files.

## Project structure

Simplified from [`ARCHITECTURE.md`](ARCHITECTURE.md). Generated trees (`.ageval/`, `.venv/`) are not source.

```text
ageval/
├── src/ageval/
│   ├── cli/                         # argv, help, exit code
│   ├── application/
│   │   ├── composition.py           # sole production wiring; CLI imports build_* here
│   │   ├── lock.py                  # load_and_lock
│   │   ├── run.py                   # mint identity → run_attempt
│   │   ├── campaign.py / suite/     # matrix · suite · Always-k
│   │   └── agent_ops/ / plugin_ops / registry_ops/
│   ├── attempt/                     # visible pipeline
│   │   ├── __init__.py              # run_attempt
│   │   └── phases/                  # environment → run → evaluate → record · cleanup
│   ├── config/                      # dataset + task.yaml + profiles
│   ├── environments/protocol.py     # EnvironmentProvider · caps; no vendor SDK
│   ├── plugins/
│   │   ├── slots.py                 # exclusive / chain
│   │   └── contrib/                 # acp · local · docker · e2b · ssh
│   ├── runtime/                     # identity, parent Agent Service, task_worker
│   ├── evaluation/                  # barrier + bind PASS
│   └── evidence/                    # trajectory.jsonl layout
├── sdk/python/                      # ageval_sdk for run.py (no PASS, no host credentials)
├── plugins/                         # external ageval.plugin/1 (nooa, dsh, miniswe, …)
├── examples/
│   ├── journeys/                    # terminal-jsonl-agg · tau2-dialog-min · multiagent-env-min
│   ├── tau3-airline/
│   └── agents/                      # ageval.agent/1
├── apps/viewer                      # ageval view SPA
├── apps/hub                         # Hub SPA
├── services/registry/               # package + results HTTP
├── docker/attempt/                  # official image; ACP entries baked in
├── docs/                            # mechanism design
└── website/                         # product docs
```

## Docs

- Usage: [`website/`](website/)
- Design: [`docs/`](docs/README.md)
- Examples: [`examples/README.md`](examples/README.md)
- [`AGENTS.md`](AGENTS.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
