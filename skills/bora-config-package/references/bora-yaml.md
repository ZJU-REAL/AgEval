# bora.yaml field notes (shipped)

## Top-level required

- `format`: must be `bora.task/1`
- `task_id`: must match `--task`
- `harness.runtime` / `harness.entrypoint`
- `provider.kind`: `local` | `docker`
- `agent_profiles`: list of `{id, executor, model}`
- `limits`: wall / agent_invocations / environment_actions / memory_mb
- `evaluation`: runtime, entrypoint, inputs, output.format

## Executors (`agent_profiles[].executor`)

**Authoritative discovery (do not hardcode):**

```bash
uv run bora executors      # .supported + host PATH probe
uv run bora executors -v   # + tools/session/stream when known
```

- **`.supported`**: adapters this BORA install provides (yaml values).
- **`.host_ready` / per-row `binary_on_path`**: host has `pi` / `opencode` / `codex` / `claude` on PATH (HTTP adapters need no binary).
- Unknown kind fails at lock (`unsupported_capability`).


## Allowlisted CLI overrides

`/parameters/seed`, `/parameters/active_profile`, `/limits/wall_time_seconds`, `/limits/agent_invocations`, `/limits/environment_actions`, `/limits/memory_mb`.

## Environment packages

- `parameters.environment_resource: postgresql` triggers parent Environment Manager prepare.
- Optional `parameters.probe_mode: undeclared_action` for deny-before-mutation public path.
- Seed SQL under `environment/seed.sql` (resource protocol only).

## Parameters conventions (non-exhaustive)

| Key | Meaning |
| --- | --- |
| `use_agent_session` | Parent Agent Service + multi-invoke |
| `active_profile` | Which profile id harness should open |

### Optional profile upstream fields

Same level as `model` (optional):

| Field | Meaning |
| --- | --- |
| `base_url` | Non-secret HTTP(S) endpoint; enters lock digest |
| `api_key` | **Environment variable name only** (locator). Value from host/repo `.env` at `bora run`; never a secret string in yaml |

Example:

```yaml
agent_profiles:
  - id: glm-coding
    executor: openai-http
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
    api_key: zhipu_coding_api_key
```
| `harness_timeout_seconds` | Worker timeout (capped by wall) |
| `workspace_output` | Terminal-class file under Attempt workspace |
| `environment_resource` | e.g. `postgresql` |

Design: `docs/design/02-task-package-and-config.md`.
