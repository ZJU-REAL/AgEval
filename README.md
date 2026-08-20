# ageval

**agent eval** — lock a dataset, open a box, run the task, let an independent evaluator own the score.

[中文](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/BORA?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/BORA/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

The GitHub repository is still `ZJU-REAL/BORA`. The product, CLI, and packages are **ageval**. There is no BORA alias.

Agent benchmarks usually score the model and leave orchestration, isolation, visibility, and the eval barrier to each vendor stack. Swap the coding agent or the box, and scores stop lining up.

**ageval** is that outer runtime: lock config, run a bounded Attempt, project what the agent can see, and bind PASS only from an independent evaluator. Coding agents enter through **ACP**. Other mechanisms install as `ageval.plugin/1` and bind from job profiles. The box is an exclusive slot: `local` / `docker` / `e2b` / `ssh`.

The Attempt pipeline is visible in `src/ageval/attempt/`. Task authors write `run.py` and `evaluator.py`, not a copy of the pipeline.

### What you can do

- Load the in-repo skills and let a coding agent pick examples, run `ageval run`, and read results
- Keep one task `run.py` and switch ACP entries (pi / Codex / Claude / OpenCode / Grok) or bind nooa / dsh from profiles
- `ageval plugin install` then bind in `profiles.yaml` — install never rewrites the dataset
- Run a full dataset (omit `--task`) or a campaign matrix
- Browse local jobs with `ageval view`
- Publish datasets to Registry / Hub; public Leaderboard is complete, release-bound suites only
- Export trajectories with `ageval evidence` — trajectory is never PASS

## Quick start

[uv](https://docs.astral.sh/uv/) and CPython **3.12+**.

```bash
git clone https://github.com/ZJU-REAL/BORA.git
cd BORA
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/core
uv run ageval lock examples/core --task config-minimal
uv run ageval run  examples/core --task acp-local-min
uv run ageval run  examples/core --task acp-docker-min --profiles examples/core/profiles.docker.yaml
uv run ageval run  examples/journeys --task terminal-jsonl-agg
uv run ageval executors -v
uv run ageval view examples/core --no-browser
```

`--probe` locks and preflights without opening a long Agent run. Missing `E2B_API_KEY` / SSH locators fail closed.

Job binding: `--profiles` replaces the dataset `profiles.yaml`. `--agent` and `--profiles` are mutually exclusive.

## Docs

In-repo docs are self-contained. You do not need an external design vault.

- Design (authority): [`docs/`](docs/README.md)
- How to use: [`website/`](website/)
- Examples: [`examples/README.md`](examples/README.md)
- Contributor routing: [`AGENTS.md`](AGENTS.md)
- Structure map: [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Layout

```text
src/ageval/          runtime
sdk/python/          ageval_sdk for run.py
plugins/             external ageval.plugin/1
examples/            named datasets
apps/viewer hub      local Jobs UI / Hub SPA
services/registry    package + results HTTP
```
