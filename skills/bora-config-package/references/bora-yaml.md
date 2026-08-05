# bora.yaml field notes (shipped)

## Top-level required

- `format`: must be `bora.task/1`
- `task_id`: must match `--task`
- `harness.runtime` / `harness.entrypoint`
- `provider.kind`: `local` | `docker`
- When `provider.kind: docker`: package file **`environment/Dockerfile`** (or
  `provider.dockerfile` override) **required** at lock time
- `agent_profiles`: list of `{id, executor, model}` (+ ACP `options.entry` when applicable)
- `limits`: wall / agent_invocations / environment_actions / memory_mb
- `evaluation`: runtime, entrypoint, inputs, output.format

## Executors (`agent_profiles[].executor`)

**Authoritative discovery (do not hardcode):**

```bash
uv run bora executors      # .supported + host readiness
uv run bora executors -v   # + tools/session/stream; .acp_entries[] for ACP
```

- **`.supported`**: kinds valid for yaml `executor:` (this BORA install).
- **Coding agents (Spec 19 Target):** `executor: acp` + `options.entry`.
- **HTTP agents:** e.g. `executor: openai-http` (+ optional `base_url` / `api_key` locator).
- Unknown kind fails at lock (`unsupported_capability`).
- Private CLI kinds (`codex` / `pi` / `opencode` / `claude-code` as **executor**) are **removed**; use ACP entry ids instead.

### ACP profiles

```yaml
agent_profiles:
  - id: codex-acp
    executor: acp
    model: entry-default          # or a model the entry accepts
    options:
      entry: codex                # registry entry_id
  - id: pi-acp
    executor: acp
    model: zai-coding-cn/glm-5.2
    api_key: glm_coding_api_key   # host env locator name only
    options:
      entry: pi
```

| Field | Rule |
| --- | --- |
| `options.entry` | **Required** when `executor: acp`. Registry ids (discover via `bora executors -v` → `acp_entries`): typically `codex`, `claude-code`, `pi`, `opencode`, `grok-build`. |
| `options.command` / `version` / `install_command` / … | **Forbidden** in package yaml (registry owns pins). |
| Host readiness | Per-entry `engine_ready` + `acp_entry_ready` in inventory — not the same as yaml `executor` kind. |

## Allowlisted CLI overrides

`/parameters/seed`, `/parameters/active_profile`, `/limits/wall_time_seconds`, `/limits/agent_invocations`, `/limits/environment_actions`, `/limits/memory_mb`.

## Environment packages

- `parameters.environment_resource: postgresql` triggers parent Environment Manager prepare.
- Optional `parameters.probe_mode: undeclared_action` for deny-before-mutation public path.
- Seed SQL under `environment/seed.sql` (resource protocol only).

## Parameters conventions (non-exhaustive)

| Key | Meaning |
| --- | --- |
| `active_profile` | Which profile id harness should open |
| `roles` | Optional map of role → profile id (multi-session harnesses) |
| `harness_timeout_seconds` | Worker timeout (capped by wall) |
| `workspace_output` | Terminal-class relative filename harness collects after invoke |
| `environment_resource` | e.g. `postgresql` |

**Agent path gate:** non-empty `agent_profiles` starts Parent Agent Service (L0) or L1 SDK session path. Empty profiles ⇒ no Agent. There is no `use_agent_session` / Runtime `question`. Prefer package `prompts/` for model text.

### Optional profile upstream fields

Same level as `model` (optional):

| Field | Meaning |
| --- | --- |
| `base_url` | Non-secret HTTP(S) endpoint; enters lock digest |
| `api_key` | **Environment variable name only** (locator). Value from host/repo `.env` at `bora run`; never a secret string in yaml |

Example (HTTP, not ACP):

```yaml
agent_profiles:
  - id: glm-coding
    executor: openai-http
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
    api_key: zhipu_coding_api_key
```

Design: `docs/design/02-task-package-and-config.md`, Spec 19 / ACP constitution.
