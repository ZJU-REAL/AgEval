---
name: bora-config-package
description: >
  Author and review BORA Databases and Task members (Database bora.yaml + tasks/*/task.yaml,
  harness/evaluator entrypoints, agent_profiles, provider local|docker, limits hard ceilings,
  artifacts, evaluation inputs, gold isolation, allowlisted overrides). Use when creating or
  editing packages under examples/, writing bora.yaml/task.yaml, adding profiles/executors,
  declaring limits, wiring evaluation inputs, or reviewing package ownership violations.
  Triggers: "bora.yaml", "task.yaml", "database", "task package", "agent_profiles",
  "evaluation gold", "workspace_output", "provider kind", "package layout". Never put secrets
  in yaml; never branch adapters by benchmark name.
---

# Config / Database + Task

Config Core is the **only** normative reader of package config. Delivery unit is a
**Database** root; each member has `task.yaml`. Harness must not re-read a second
“true config” over lock.

CLI: `bora lock|run <database-root> --task <task_id>` · `bora tasks <database-root>`.

## Layout

```text
my-database/                 # CLI path (bora.database/1)
├── bora.yaml                # Database identity / version / tasks.root
└── tasks/
    └── my-task/             # task_id == directory name
        ├── task.yaml        # bora.task/1 — execution contract
        ├── harness.py
        ├── evaluator.py
        ├── environment/     # optional seed.sql; Docker L1 needs Dockerfile
        ├── evaluation/      # gold / hidden — not for Agent mount
        ├── lib/
        └── data/
```

## Minimal Database `bora.yaml`

```yaml
format: bora.database/1
database_id: org/my-suite
version: "0.1.0"
tasks:
  root: tasks
# optional defaults (suite scheduling only):
# defaults:
#   max_concurrent_tasks: 1
```

## Minimal member `task.yaml` skeleton

```yaml
format: bora.task/1
task_id: my-task

harness:
  runtime: python
  entrypoint: harness:run

parameters:
  # active_profile: opencode-acp   # optional; overridable via CLI --set
  # Non-empty agent_profiles ⇒ Agent Service; harness owns session/invoke.

provider:
  kind: local               # or docker for L1
  assurance: l0             # docker L1 packages use assurance: l1 intent

agent_profiles:
  # Coding agents (Spec 19): executor: acp + options.entry — NOT executor: codex|pi|…
  - id: opencode-acp
    executor: acp
    model: entry-default    # or a provider-qualified model id
    options:
      entry: opencode       # registry: codex | claude-code | pi | opencode | grok-build
  - id: pi-acp
    executor: acp
    model: zai-coding-cn/glm-5.2
    api_key: glm_coding_api_key   # env *locator name* only
    options:
      entry: pi

limits:
  wall_time_seconds: 300
  agent_invocations: 2
  environment_actions: 0

artifacts:
  publishable:
    - id: session-output
      producer: harness
      path: artifacts/session-output.json
      media_type: application/json

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: session-output
      target: artifacts/session-output.json
  output:
    format: json
```

HTTP / non-ACP profile example:

```yaml
  - id: glm-coding
    executor: openai-http
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
    api_key: zhipu_coding_api_key
```

## Ownership rules

| Field | Consumer |
| --- | --- |
| `parameters` | Harness `ctx.params` only |
| envelope / profiles / limits / provider | Runtime |
| gold under `evaluation/` | Clean evaluator after barrier — **not** Agent/Harness mount |

- Never put API keys or passwords in yaml.
- Do not branch harness on executor kind / ACP entry for Core behavior; switch profile instead.
- Adapter modules must stay mechanism-named (`acp`, `postgresql`, docker) — not benchmark names.

## Which `executor` / ACP `entry` values?

```bash
uv run bora executors          # .supported + host readiness
uv run bora executors -v       # + acp_entries[] (entry_id, engine/acp readiness, credential env *names*)
```

| Surface | Meaning |
| --- | --- |
| `.supported` | Valid `agent_profiles[].executor` values (this install): typically `acp`, `openai-http`, … |
| `.acp_entries[]` | When `executor: acp`, valid `options.entry` ids + host binary readiness |
| `.host_ready` | Kinds that can run here (ACP needs at least one ready entry; HTTP needs no CLI) |

**Target (coding agents):** `executor: acp` + `options.entry: <registry-id>`.  
**Do not** write `executor: codex|pi|opencode|claude-code` — lock fails (`unsupported_capability`) or L1 fails (`migrated_to_acp`).

Do not invent kinds or entry ids.

## Profile switch without harness edits

1. Add/edit `agent_profiles` entries (and optional `parameters.roles` / `active_profile`).
2. Or CLI: `bora run ... --set '/parameters/active_profile="pi-acp"'` (allowlisted).

## Detail

- Field catalog & allowlists: [references/bora-yaml.md](references/bora-yaml.md)
- Isolation / gold / L1 notes: [references/isolation.md](references/isolation.md)
