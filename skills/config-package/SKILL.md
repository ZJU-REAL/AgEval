---
name: bora-config-package
description: How to write bora.yaml Task Packages without violating ownership red lines.
---

# Config / Task Package

## Layout

```text
my-package/
  bora.yaml
  harness.py          # entrypoint
  evaluator.py        # independent score
  environment/        # optional seed.sql
  evaluation/         # gold — not mounted to Agent
  lib/                # package tools
```

## Minimal `bora.yaml` fields

- `format: bora.task/1`, `task_id`
- `harness.runtime` + `entrypoint`
- `provider.kind` (`local` | `docker`)
- `agent_profiles[]` with `id`, `executor`, `model`
- `limits.agent_invocations` / `environment_actions` / `wall_time_seconds`
- `evaluation` inputs from published artifacts only

## Ownership rules

- `parameters` → harness (`ctx.params`); envelope → Runtime.
- Never put API keys or passwords in yaml.
- Gold under `evaluation/` must not be visible to harness/agent (Docker L1 filters).

## Profile switch

Change `agent_profiles` or `--set /parameters/active_profile=...` — do **not** branch harness on executor kind.

Design: `docs/design/02-task-package-and-config.md`
