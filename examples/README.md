# BORA examples

Tracked Task Packages used as public smokes, expected-failure probes, and
case-class journeys. Packages live under **category folders** — not a flat list.

```text
examples/
├── README.md                 ← this file
├── journeys/                 ← case-class fidelity (env / multiagent / tau2 / terminal)
├── core/                     ← Core surface smokes (config / harness / eval / agent / SDK)
└── l1/                       ← Provider L1 isolation probes
```

Each leaf package is a self-contained Task Package (`bora.yaml` + entrypoints)
with a local **`README.md`** that explains what the task is for (user-facing).
Run from the **repo root** with the package directory as the path argument:

```bash
uv run bora lock examples/<category>/<package> --task <task_id>
uv run bora run  examples/<category>/<package> --task <task_id>
```

## Agent scheduling

- **Non-empty `agent_profiles`** ⇒ Runtime starts Parent Agent Service (L0) or L1 SDK
  session path; harness owns every `Agent.session` / `invoke`.
- **Empty `agent_profiles`** ⇒ no Agent path (config/harness/tool/env/L1 probes).
- There is **no** `parameters.use_agent_session` and **no** Runtime
  `parameters.question` one-shot. Prompts live under package `prompts/` (or harness).

## `journeys/` — case-class demos

| Package | Case class | Surfaces |
| --- | --- | --- |
| [`env-postgres-min`](journeys/env-postgres-min/) | Environment + DB tool | Environment Manager, seed, `lib/` tools (no agent) |
| [`multiagent-env-min`](journeys/multiagent-env-min/) | multiagentbench class | Multi-session roles, SQL tools, sealed gold |
| [`tau2-dialog-min`](journeys/tau2-dialog-min/) | tau2 retail class | User-sim + service tools, mutable state |
| [`terminal-jsonl-agg`](journeys/terminal-jsonl-agg/) | terminal-bench class | L1 workspace file + filtered mounts + clean eval |

## `core/` — Core surface gates

| Package | Role |
| --- | --- |
| [`config-minimal`](core/config-minimal/) | `bora lock` success |
| [`config-invalid`](core/config-invalid/) | `bora lock` expected-failure |
| [`harness-minimal`](core/harness-minimal/) | Worker harness, no agent |
| [`evaluator-negative`](core/evaluator-negative/) | Harness `completed` ≠ PASS |
| [`sdk-agent-session`](core/sdk-agent-session/) | Parent-bound multi-invoke + PASS |
| [`plugin-agent-executor`](core/plugin-agent-executor/) | Second executor (`openai-http`) |
| [`attempt-trajectory`](core/attempt-trajectory/) | §8.9 trajectory + `Result.logs` |
| [`hard-ceiling-trajectory`](core/hard-ceiling-trajectory/) | N+1 invoke denied pre-effect |
| [`builtin-executor-conformance`](core/builtin-executor-conformance/) | Profile-only ACP entry switch（五 entry：codex/pi/opencode/claude-code/grok-build） |
| [`builtin-executor-mixed`](core/builtin-executor-mixed/) | Same Attempt dual profile trajectories |
| [`sdk-tool-guard`](core/sdk-tool-guard/) | ToolSet + call limit success |
| [`sdk-tool-guard-denied`](core/sdk-tool-guard-denied/) | Tool policy denial |
| [`environment-action-denied`](core/environment-action-denied/) | Env undeclared/dangerous action deny |

## `l1/` — Provider L1 isolation

| Package | Role |
| --- | --- |
| [`sdk-session-single-actor`](l1/sdk-session-single-actor/) | L1 SDK session → attempt-container PASS |
| [`executor-image-official`](l1/executor-image-official/) | Dockerfile `FROM bora-attempt:l1` |
| [`executor-image-upstream`](l1/executor-image-upstream/) | Upstream base + install-executors |
| [`multi-agent-shared-container`](l1/multi-agent-shared-container/) | shared-container multi-UID |
| [`multi-agent-container-per-group`](l1/multi-agent-container-per-group/) | container-per-group |
| [`provider-l1-denied`](l1/provider-l1-denied/) | Hidden material / gold denial |
| [`provider-l1-projection-denied`](l1/provider-l1-projection-denied/) | Credential / network projection denial |
| [`provider-l1-residual-writer`](l1/provider-l1-residual-writer/) | Writer stop before evaluator barrier |

## What was removed (this cleanup)

| Former package | Reason |
| --- | --- |
| `core/agent-eval` | Absorbed by `sdk-agent-session` |
| `core/acp-agent-conformance` | Covered by `builtin-executor-conformance` |
| `core/orchestration-environment` | Covered by `journeys/multiagent-env-min` |
| `l1/provider-l1-agent-eval` | Covered by `sdk-session-single-actor` |
| `l1/builtin-executor-visibility` | Location covered by single-actor |
| `l1/builtin-executor-visibility-denied` | Covered by `provider-l1-denied` |
| `l1/acp-agent-placement` | Covered by L1 SDK session packages |
| `echo-contract` / `workspace-file-eval` | Earlier redundancy |

## Suggested first runs

```bash
uv run bora lock examples/core/config-minimal --task config-minimal
uv run bora lock examples/core/config-invalid --task config-invalid   # expect exit 2
uv run bora run examples/core/sdk-agent-session --task sdk-agent-session
uv run bora run examples/journeys/terminal-jsonl-agg --task terminal-jsonl-agg
```
