---
name: bora-config-package
description: >
  Author and review BORA Task Packages (bora.yaml layout, harness/evaluator entrypoints,
  agent_profiles, provider local|docker, limits hard ceilings, artifacts, evaluation inputs,
  gold isolation, allowlisted overrides). Use when creating or editing packages under
  examples/, writing bora.yaml, adding profiles/executors, declaring limits, wiring
  evaluation inputs, or reviewing package ownership violations. Triggers: "bora.yaml",
  "task package", "agent_profiles", "evaluation gold", "workspace_output", "provider kind",
  "package layout". Never put secrets in yaml; never branch adapters by benchmark name.
---

# Config / Task Package

Config Core is the **only** normative reader of package config. Harness must not re-read a second “true config” over lock.

## Package layout

```text
my-package/
├── bora.yaml              # required
├── harness.py             # or path from harness.entrypoint
├── evaluator.py           # independent scorer
├── environment/           # optional seed.sql (resource protocol)
├── evaluation/            # gold / hidden — not for Agent mount
├── lib/                   # package-local tools/helpers
└── data/                  # optional seeds for workspace tasks
```

## Minimal `bora.yaml` skeleton

```yaml
format: bora.task/1
task_id: my-task

harness:
  runtime: python
  entrypoint: harness:run

parameters:
  use_agent_session: true   # parent Agent Service multi-invoke
  # active_profile: codex-mini   # optional; overridable via CLI --set

provider:
  kind: local               # or docker for L1
  assurance: l0             # docker L1 packages use assurance: l1 intent

agent_profiles:
  - id: codex-mini
    executor: codex         # see: uv run bora executors  → .supported
    model: gpt-5.4-mini

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

## Ownership rules

| Field | Consumer |
| --- | --- |
| `parameters` | Harness `ctx.params` only |
| envelope / profiles / limits / provider | Runtime |
| gold under `evaluation/` | Clean evaluator after barrier — **not** Agent/Harness mount |

- Never put API keys or passwords in yaml.
- Do not branch harness on executor kind for Core behavior; switch profile instead.
- Adapter modules must stay mechanism-named.

## Which `executor` values?

```bash
uv run bora executors          # .supported + PATH binary probe
uv run bora executors -v       # + capability fields
```

- `.supported` — kinds this BORA install provides (write these in yaml)
- `.host_ready` — can actually run here (binary on PATH, or pure HTTP adapter)
- `.missing_binary` — need to install/export that CLI first

Do not invent kinds.

## Profile switch without harness edits

1. Add/edit `agent_profiles` entries.
2. Or CLI: `bora run ... --set '/parameters/active_profile="pi-mini"'` (allowlisted).

## Detail

- Field catalog & allowlists: [references/bora-yaml.md](references/bora-yaml.md)
- Isolation / gold / L1 notes: [references/isolation.md](references/isolation.md)
