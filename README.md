# ageval

**agent eval** — lock a dataset, pick an environment, run the task, let an independent evaluator own the score.

[中文](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/ageval?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/ageval/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

Agent benchmarks usually score the model and leave orchestration, isolation, visibility, and the eval barrier to each vendor stack. Swap the coding agent or the environment, and scores stop lining up.

**ageval** is that outer runtime: lock config, run a bounded Attempt, project what the agent can see, and bind PASS only from an independent evaluator. Coding agents enter through **ACP**. Other mechanisms install as `ageval.plugin/1` and bind from job profiles. The environment is an exclusive slot: `local` / `docker` / `e2b` / `ssh`.

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

Swap the environment or the Agent; the task `run.py` stays.

### What you can do

- Load the in-repo skills and let a coding agent pick examples, run `ageval run`, and read results
- Keep one task `run.py` and switch ACP entries (pi / Codex / Claude / OpenCode / Grok) or bind nooa / dsh / miniswe from profiles
- `ageval plugin install` then bind in `profiles.yaml` — install never rewrites the dataset
- Run a full dataset (omit `--task`) or a campaign matrix
- Browse local jobs with `ageval view`
- Publish datasets to Registry / Hub; public Leaderboard is complete, release-bound suites only
- Export trajectories with `ageval evidence`

## Quick start

[uv](https://docs.astral.sh/uv/) and CPython **3.12+**.

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

Default `examples/journeys` profiles use `environment: docker`. `--probe` locks and preflights without opening a long Agent run. Missing `E2B_API_KEY` / SSH locators fail closed.

Job binding: `--profiles` replaces the dataset `profiles.yaml`. `--agent` and `--profiles` are mutually exclusive.

## Docs

- Design: [`docs/`](docs/README.md)
- How to use: [`website/`](website/)
- Examples: [`examples/README.md`](examples/README.md)
- [`AGENTS.md`](AGENTS.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Layout

```text
src/ageval/          runtime
sdk/python/          ageval_sdk for run.py
plugins/             external ageval.plugin/1
examples/            named datasets
apps/viewer hub      local Jobs UI / Hub SPA
services/registry    package + results HTTP
```
