# BORA

**Bounded Orchestration for Runtime Agents**

[中文文档](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/ffy6511/BORA?display_name=tag&sort=semver)](https://github.com/ffy6511/BORA/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![Issues](https://img.shields.io/github/issues/ffy6511/BORA)](https://github.com/ffy6511/BORA/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/ffy6511/BORA)](https://github.com/ffy6511/BORA/pulls)

---

Agent benchmarks usually score the model and leave the **harness**—orchestration, isolation, visibility, and evaluation boundaries—to each vendor’s private stack. Swap the coding agent, isolation mode, or upstream framework, and scores stop lining up; reproduction and trajectories fragment the same way.

**BORA** is that outer runtime: lock task config, run a bounded Attempt, control what the agent can see, and let an independent evaluator own the score. Coding agents go through **ACP**, so popular ACP-capable harnesses plug in for evaluation without a new scraper in Core.

### What you can do with it

- **Automate evaluation with agent + skill** — after clone, load the repo skills so a coding agent can pick examples, run `bora run`, and read results and trajectories for you
- **Compose Harness × Agent × Model freely** — keep one task harness and switch Codex / Claude / Pi / OpenCode (and models) via ACP for near-cartesian comparison—no per-vendor stdout scraper
- **Drop an existing harness into a shared boundary** — keep your workflow; the outer layer unifies config lock, isolation (host / Docker), visibility, and independent scoring for cross-framework reproduction
- **Batch a full Dataset or a parameter matrix** — run every task in a suite, or campaign over allowlisted overrides such as seed / profile
- **Aggregate suite scores and archive job results** — suite runs write observational `pass_rate` / `mean_score` ; upload/list suite rows on the Registry when you need a shared results store
- **Browse local suite runs in a Web UI** — `bora view` opens a Jobs → Tasks → Trial console over `.bora/suite-runs/`
- **Review and export trajectories** — each invoke lands on disk; `bora evidence` exports a sealed copy for failure analysis or training pipelines

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and CPython **3.12+**.

```bash
git clone https://github.com/ffy6511/BORA.git
cd BORA
uv sync --frozen --all-packages
uv run bora -V
```

### Common CLI

```bash
# List tasks in a Dataset
uv run bora tasks examples/core

# Lock only (no agent / evaluator)
uv run bora lock examples/core --task config-minimal

# Real multi-turn agent path (host ACP entry + credentials required)
uv run bora run examples/core --task sdk-agent-session

# Switch coding-agent entry via allowlisted override
uv run bora run examples/core --task builtin-executor-conformance \
  --set '/parameters/active_profile="pi-mini"'

# Full Dataset suite (omit --task)
uv run bora run examples/core --max-concurrent-tasks 2

# Local results console (build SPA once: cd apps/viewer && pnpm build)
uv run bora view examples/core --no-browser

# List executor kinds / ACP entries ready on this host
uv run bora executors -v
```

### Let a coding agent drive it

Skills under [`skills/`](skills/) are discoverable via [`.agents/skills`](.agents/skills). Point your agent at them to run a Dataset under `examples/`, or edit `harness.py` yourself.

| Skill                                                | Use when                          |
| ---------------------------------------------------- | --------------------------------- |
| [`bora-platform`](skills/bora-platform/)             | Product map and red lines         |
| [`bora-cli`](skills/bora-cli/)                       | CLI and result interpretation     |
| [`bora-config-package`](skills/bora-config-package/) | Authoring Dataset / task config   |
| [`bora-sdk-harness`](skills/bora-sdk-harness/)       | Writing harnesses with `bora_sdk` |

---

## Reading a package

A **Dataset** is the delivery unit: root `bora.yaml` plus member tasks.

```text
examples/core/                    # one Dataset
├── bora.yaml                     # suite metadata, tasks root
└── tasks/
    └── sdk-agent-session/
        ├── task.yaml             # harness, provider, agent_profiles, limits, evaluation
        ├── harness.py            # workflow inside the Attempt
        ├── evaluator.py          # independent PASS/FAIL
        └── …
```

| Path                                       | Role                                               |
| ------------------------------------------ | -------------------------------------------------- |
| [`examples/core/`](examples/core/)         | Core smokes                                        |
| [`examples/journeys/`](examples/journeys/) | Case demos (env / multi-agent / dialog / terminal) |
| [`examples/l1/`](examples/l1/)             | Docker L1 probes                                   |

CLI takes the **Dataset root**; `--task <id>` selects a member. Full list: [`examples/README.md`](examples/README.md).

```yaml
agent_profiles:
  - id: codex-mini
    executor: acp
    options:
      entry: codex # see: bora executors
    model: gpt-5.4-mini
```

---

## Reading run outputs

Per-task Attempt evidence lands under the member at `tasks/<task_id>/.bora/runs/<run_id>/`:

```text
tasks/<task_id>/.bora/runs/<run_id>/
├── lock.json              # locked config snapshot (no secrets)
├── result.json            # flat Result (status, score, …)
├── summary.json
├── harness.json           # harness terminal / publish facts
├── agent.json
├── effects.jsonl
├── cleanup.json
└── agent/
    ├── events.jsonl
    └── invocations/
        └── 0001-<inv_id>/
            ├── request.json
            ├── final-response.json
            ├── metadata.json
            ├── events.jsonl
            ├── trajectory.jsonl   # turn-level rows (when produced)
            └── backend_raw/       # redacted backend stream
```

`bora run` prints a single JSON object: `status` / `score` are the evaluation verdict; `logs` is the absolute path to this Attempt’s evidence root.

```bash
uv run bora evidence "$LOGS_PATH" --out /tmp/bora-export
```

A **full suite** (omit `--task`) also writes observational aggregates at the Dataset root:

```text
.bora/suite-runs/<suite_run_id>/summary.json   # metrics.pass_rate / mean_score, task_refs
```

PASS remains per-task only. Optional Registry archive: `bora results upload-suite` (see CLI README). Local UI: `bora view <dataset>`.

---

## Further reading

| Audience  | Start here                                                   |
| --------- | ------------------------------------------------------------ |
| Design    | [`docs/design/`](docs/design/)                               |
| Structure | [`ARCHITECTURE.md`](ARCHITECTURE.md)                         |
| CLI       | [`src/bora/cli/README.md`](src/bora/cli/README.md)           |
| Viewer    | [`apps/viewer/README.md`](apps/viewer/README.md)             |
| Registry  | [`services/registry/README.md`](services/registry/README.md) |
| Releases  | [Releases](https://github.com/ffy6511/BORA/releases)         |
