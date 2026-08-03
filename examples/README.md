# BORA examples

Tracked Task Packages used as public smokes, expected-failure probes, and
case-class journeys. Packages live under **category folders** — not a flat list.

```text
examples/
├── README.md                 ← this file
├── journeys/                 ← case-class fidelity (env / multiagent / tau2 / terminal)
├── core/                     ← Core surface smokes (config / harness / eval / agent / SDK / plugin)
└── l1/                       ← Provider L1 isolation probes
```

Each leaf package is a self-contained Task Package (`bora.yaml` + entrypoints).
Run from the **repo root** with the package directory as the path argument:

```bash
uv run bora lock examples/<category>/<package> --task <task_id>
uv run bora run  examples/<category>/<package> --task <task_id>
```

## `journeys/` — case-class demos

Product-shaped packages that map v1 benchmark *classes* onto BORA Core surfaces
(not `*BenchAdapter` clones). Prefer these when validating “can we run real work”.

| Package | Case class | Surfaces |
| --- | --- | --- |
| [`env-postgres-min`](journeys/env-postgres-min/) | Environment + DB tool smoke | Environment Manager, package seed, `lib/` tools, no agent on default path |
| [`multiagent-env-min`](journeys/multiagent-env-min/) | multiagentbench / database-52 class | Multi-invoke roles, real SQL tools, sealed gold labels |
| [`tau2-dialog-min`](journeys/tau2-dialog-min/) | tau2-bench retail class | User-sim + service tools, mutable state, order gate |
| [`terminal-jsonl-agg`](journeys/terminal-jsonl-agg/) | terminal-bench / jsonl-aggregator | Workspace file output, L1 filtered mounts + clean evaluator |

## `core/` — Core surface gates

Thin packages that pin individual Core / Harness Core contracts. Keep these for
regression of config lock, harness entry, evaluation barrier, agent invoke, and
SDK helpers — not as full case fidelity demos.

| Package | Role |
| --- | --- |
| [`config-minimal`](core/config-minimal/) | `bora lock` success (deterministic summary) |
| [`config-invalid`](core/config-invalid/) | `bora lock` expected-failure (`unknown_profile`) |
| [`harness-minimal`](core/harness-minimal/) | Worker harness entry, params → publish → terminal (no agent) |
| [`evaluator-negative`](core/evaluator-negative/) | Harness `completed` ≠ PASS (independent FAIL) |
| [`agent-eval`](core/agent-eval/) | Single real Agent invoke + independent PASS |
| [`sdk-agent-session`](core/sdk-agent-session/) | Parent-bound multi-invoke `AgentSession` |
| [`sdk-tool-guard`](core/sdk-tool-guard/) | `ToolSet` + call limit success |
| [`sdk-tool-guard-denied`](core/sdk-tool-guard-denied/) | Tool policy denial (pre-callable) |
| [`plugin-agent-executor`](core/plugin-agent-executor/) | Second executor profile (e.g. OpenAI HTTP) via same harness |

## `l1/` — Provider L1 isolation

Docker assurance probes. Positive path plus isolation negatives (hidden material,
projection, residual writer). Not substitutes for the journey packages.

| Package | Role |
| --- | --- |
| [`provider-l1-agent-eval`](l1/provider-l1-agent-eval/) | L1 Attempt + agent + clean evaluator PASS |
| [`provider-l1-denied`](l1/provider-l1-denied/) | Hidden material / view denial |
| [`provider-l1-projection-denied`](l1/provider-l1-projection-denied/) | Credential / network projection denial |
| [`provider-l1-residual-writer`](l1/provider-l1-residual-writer/) | Residual writer stop before evaluator |

## What was removed

| Former package | Reason |
| --- | --- |
| `echo-contract` | Redundant with `core/agent-eval` (single Codex JSON PASS) |
| `workspace-file-eval` | Redundant with `journeys/terminal-jsonl-agg` (workspace aggregates path) |

## Suggested first runs

```bash
# Config gates (fast, no agent)
uv run bora lock examples/core/config-minimal --task config-minimal
uv run bora lock examples/core/config-invalid --task config-invalid   # expect exit 2

# Journeys (need Docker and/or Codex depending on package)
uv run bora run examples/journeys/env-postgres-min --task env-postgres-min
uv run bora run examples/journeys/multiagent-env-min --task multiagent-env-min
uv run bora run examples/journeys/tau2-dialog-min --task tau2-dialog-min
uv run bora run examples/journeys/terminal-jsonl-agg --task terminal-jsonl-agg
```

See each package’s local `README.md` (when present) for layout and constraints.
