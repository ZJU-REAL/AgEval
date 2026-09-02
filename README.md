# ageval

<p align="center">
  <img src="docs/assets/hero.png" alt="ageval: Write your agent eval once. Run it anywhere." width="100%">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">中文</a>
</p>

<p align="center">
  <a href="https://github.com/ZJU-REAL/ageval/stargazers"><img alt="stars" src="https://shieldcn.dev/github/stars/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoStarFill&logoColor=F5C518"></a>
  <a href="https://github.com/ZJU-REAL/ageval/blob/main/LICENSE"><img alt="license" src="https://shieldcn.dev/github/license/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AFaBalanceScale&logoColor=34D399"></a>
  <a href="https://github.com/ZJU-REAL/ageval/releases"><img alt="release" src="https://shieldcn.dev/github/release/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoTag&logoColor=60A5FA"></a>
  <a href="https://github.com/ZJU-REAL/ageval/commits"><img alt="last commit" src="https://shieldcn.dev/github/last-commit/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoGitCommit&logoColor=A78BFA"></a>
</p>

Most agent evaluation still measures the **model**: same prompts, same tool contract, different weights or APIs. A shippable agent is a model plus its runtime — the same weights on a different coding agent, tool policy, or environment behave differently and cost differently. A comparison that deserves the name is a product: **H agent runtimes × M models × E environments**. Every cell wants its own scaffold; scores mean nothing unless that cell is in the lock.

**ageval** turns that product from code into configuration. A dataset (`run.py` + `evaluator.py`) is written once; environment and Agent bind in `profiles.yaml` through plugins and lock with the model into one reproducible digest. The Hub publishes datasets, plugins, and Agent packages. The public leaderboard lists complete, release-bound dataset runs only.

<p align="center">
  <img src="docs/assets/why-ageval.jpg" alt="N environments × M agent runtimes: each combination would need its own scaffold; ageval composes environment and Agent through plugins, so one dataset runs anywhere." width="800">
</p>

## Contents

- [What it is](#what-it-is)
- [How it works](#how-it-works)
- [Features](#features)
- [Getting started](#getting-started)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Docs](#docs)

## What it is

Write a dataset once. Swap the environment and the Agent without rewriting `run.py`. A score has to name which agent runtime and which environment ran it, not only the model.

- **The unit of delivery is a dataset.** A dataset holds tasks; each task owns the loop (`run.py`), the score (`evaluator.py`), and gold. Environment and Agent bind in `profiles.yaml`, not in the dataset.
- **An Attempt is something you can open.** Order is environment → run → evaluate → record; cleanup always runs. The directory is `.ageval/runs/<id>/`.
- **Change the environment without changing the task.** Host, Docker, or a cloud sandbox / remote ([e2b](https://e2b.dev), ssh, [daytona](https://www.daytona.io)). Missing capability or credentials fail at `ageval lock`; the run does not start.
- **Coding agents enter through plugins.** Default is [ACP](https://agentclientprotocol.com) ([pi](https://pi.dev), [Codex](https://github.com/openai/codex), [Claude Code](https://github.com/anthropics/claude-code), [OpenCode](https://github.com/sst/opencode)); [nooa](https://github.com/NVIDIA-NeMo/labs-OO-Agents), [dsh](https://github.com/deepseek-ai/deepseek-harness), and [miniswe](https://github.com/SWE-agent/mini-swe-agent) join the same way and use the same Attempt path and leaderboard.
- **Results have a home.** The local Viewer opens an Attempt under Jobs → Tasks. The Hub publishes datasets, plugins, and Agent packages. The public leaderboard lists complete, release-bound suites only.

## How it works

```text
            you ── lock / run ──►  ┌─────────────────┐
                                   │     Attempt     │  lock dataset · digest
                                   │   ageval Core   │  environment → run
                                   │                 │  evaluate → record
                                   │                 │  finally cleanup
                                   └────────┬────────┘
                                            │ opens one environment
              ┌─────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
        ┌───────────┐                 ┌───────────┐                 ┌───────────┐
        │   local   │                 │  docker   │                 │ e2b/ssh/daytona │
        └─────┬─────┘                 └─────┬─────┘                 └─────┬─────┘
              └──────── Protocol: upload · exec · attach_stdio ───────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │     run.py      │  task loop · Agent invoke
                                   │  ACP / plugin   │  plugin inlet
                                   └────────┬────────┘
                                            ▼
                                   ┌─────────────────┐
                                   │  evaluator.py   │  only source of PASS
                                   └─────────────────┘
```

1. **lock.** Dataset, environment, and Agent compose into a digest. Secrets stay locators; they are not stored as plaintext in the lock.
2. **Open an environment.** Host, Docker, a cloud sandbox, or a remote. Missing capability or credentials fail before the environment opens.
3. **Run `run.py`.** Loop, tools, and Agent invocation live here. Changing the environment or the Agent does not require rewriting this file.
4. **Score independently.** Gold enters the environment at this phase. `evaluator.py` binds PASS / FAIL / ERROR. Cleanup always runs.

## Features

**Evaluation**

- **One lock.** Dataset, agent runtime, and environment go into the same lock and yield a reproducible digest.
- **One task, a suite, a matrix, or repeats.** Run a single task, a full dataset, a parameter matrix on one task, or multiple independent Attempts of the same `profiles.yaml` (pass@k).
- **Scoring is separate from the Agent.** Gold does not enter files the Agent can see. PASS comes only from `evaluator.py` (deterministic script by default; optional `Agent.session` as LLM-as-judge). Trajectories are for inspection.
- **limits are enforced before invocation.** Wall time, memory, processes, and invocation counts are set by the runtime before invoke.

**Composition**

- **One `run.py` under each binding.** Environment and Agent combine through plugins. Default is [ACP](https://agentclientprotocol.com); [nooa](https://github.com/NVIDIA-NeMo/labs-OO-Agents), [dsh](https://github.com/deepseek-ai/deepseek-harness), and [miniswe](https://github.com/SWE-agent/mini-swe-agent) join through the same plugin path and the same Attempt path and leaderboard.
- **Agent packages.** Format `ageval.agent/1` (executor, entry, overlays). Built-in packages bind with `--agent pi` (no install). Custom overlay packs still `ageval agent install` then `--agent org/name@version`. `binding.model` is the default; `--model` overrides this run.
- **Multiple roles and sessions.** The task owns dialog, tools, and handoff; the runtime supplies the environment and the Agent inlet.
- **Validate before invoke.** Capabilities and credentials are checked before the Agent is called; absence fails and invoke does not start.

**Environment**

- **Host, container, cloud sandbox, remote.** local, docker, [e2b](https://e2b.dev), ssh, [daytona](https://www.daytona.io): `upload` / `exec` / `attach_stdio`.
- **The Agent sees only the projected workspace.** Gold and host credentials do not enter the dataset default environment.
- **Official Attempt image.** Docker installs ACP entries at build time; they are not installed at invoke.

**Results**

- **Local Viewer.** Inspect trajectory, environment, and score along Jobs → Tasks → Attempt.
- **Sealed trajectory.** Export a copy without modifying the score.
- **Hub.** Publish datasets, plugins, and Agent packages; upload suites. Organizations manage members, public/private scope, and versions. The public Leaderboard lists complete, release-bound suites only. Operators can `docker compose -f services/registry/docker-compose.yml up -d` (Postgres, object store, Registry, Hub) and pull `ghcr.io/zju-real/ageval-hub` / `ageval-registry` from a release tag.

**Authoring**

- **The task owns only that task.** Loop, tools, scoring, and gold; orchestration does not belong in the task.
- **SDK is optional.** Sessions, tools, terminals. It does not decide PASS and does not hold host credentials.

## Getting started

Install the CLI from PyPI. Requires CPython **3.12+**. A live coding-agent run also requires a host ACP entry and credentials. `ageval lock` does not.

```bash
uv tool install ageval-cli
ageval -V
```

Optional backends ship as extras: `e2b`, `daytona`, `registry`, `nooa`, `dsh`, `miniswe` — or everything at once:

```bash
uv tool install 'ageval-cli[all]'
```

Run a dataset straight from the Hub by registry ref (`<dataset_id>@<version>`), or any local dataset root:

```bash
ageval registry list                        # datasets visible on the Hub
ageval run <org>/<name>@<version> --task <task-id>
ageval executors -v
ageval view <org>/<name>@<version> --no-browser
```

Default profiles use `environment: docker` (a working Docker engine is needed). Bind a shipped Agent package with `--agent pi` (no install). Optional `--model` overrides this run. Custom overlay packs use `ageval agent install` then `--agent org/name@version`. Missing extras or credentials fail the check and the run does not start; the error includes the exact install command.

Skills for your coding agent (CLI, plugins, dataset authoring, `run.py`/SDK):

```bash
npx skills add ZJU-REAL/ageval
```

### Develop from source

The in-repo examples — [`examples/README.md`](examples/README.md): `minimal-demo`, a five-task `tau3-airline-5` cut, and catalog Agents — need a repo checkout:

```bash
git clone https://github.com/ZJU-REAL/ageval.git
cd ageval
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/datasets/minimal-demo
uv run ageval lock examples/datasets/minimal-demo --task terminal-jsonl-agg
uv run ageval run  examples/datasets/minimal-demo --task terminal-jsonl-agg
uv run ageval run  examples/datasets/minimal-demo --task terminal-jsonl-agg --probe
uv run ageval view examples/datasets/minimal-demo --no-browser
```

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

- lock is the normative gate: unknown format fails once. Plugins change the binding, not the environment → run → evaluate → record phases.
- An Attempt owns identity, deadlines, cleanup, and the score.
- Local Viewer reads files; Hub talks to Registry.

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
│   ├── attempt/                     # Attempt pipeline
│   │   ├── __init__.py              # run_attempt
│   │   └── phases/                  # environment → run → evaluate → record · cleanup
│   ├── config/                      # dataset + task.yaml + profiles
│   ├── environments/protocol.py     # EnvironmentProvider · caps; no vendor SDK
│   ├── plugins/
│   │   ├── slots.py                 # exclusive / chain
│   │   └── contrib/                 # acp · local · docker · e2b · daytona · ssh
│   ├── runtime/                     # identity, parent Agent Service, task_worker
│   ├── evaluation/                  # bind PASS
│   └── evidence/                    # trajectory.jsonl layout
├── src/ageval_sdk/                  # ageval_sdk for run.py (no PASS, no host credentials)
├── plugins/                         # external ageval.plugin/1 (nooa, dsh, miniswe, …)
├── examples/
│   ├── datasets/
│   │   ├── minimal-demo/            # terminal-jsonl-agg · tau2-dialog-min · multiagent-env-min
│   │   └── tau3-airline-5/            # airline-00 … airline-04
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
