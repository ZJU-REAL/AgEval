# Database `bora.yaml` + member `task.yaml` field notes (shipped)

## Database root (`bora.yaml`)

- `format`: must be `bora.database/1`
- `database_id`: charset `^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$` (1–128); no `..` / `//`
- `version`: non-empty string
- `tasks.root`: default `tasks`
- `defaults` v1 allowlist: only `max_concurrent_tasks` (≥1)
- Optional `provenance` (suite default; see below)
- **Forbidden** on root: harness / provider / limits / evaluation / agent_profiles / …

## Member (`task.yaml`) — top-level required

- `format`: must be `bora.task/1`
- `task_id`: must match directory name and CLI `--task`
- `harness.runtime` / `harness.entrypoint`
- `provider.kind`: `local` | `docker`
- When `provider.kind: docker`: package file **`environment/Dockerfile`** (or
  `provider.dockerfile` override) **required** at lock time
- `agent_profiles`: role slots only (`{id}`); executor / model / `options` live in Database `profiles.yaml`
- `limits`: wall / agent_invocations / environment_actions / memory_mb
- `evaluation`: runtime, entrypoint, inputs, output.format; optional `network`
  (`none` only); optional `tmpfs_mb` (positive int, L1 `/tmp` MiB, default 32);
  optional `placement` (`staging` \| `writable`); optional `timeout_seconds`.
  **Not** `limits.*`. `writable` allows exec on `/tmp` and sets
  `BORA_EVAL_WORKDIR`; still `--read-only` root. Size stays `tmpfs_mb`.
- Optional `provenance` (fully replaces Database-root default when set)

## Provenance (optional)

Declare where a package/task was ported from. **Not PASS** and not a quality score.

```yaml
provenance:
  kind: port   # port | reimplementation | wrapper | original
  upstream:
    name: tau-bench
    url: https://github.com/example/tau-bench
    ref: v0.1.0          # and/or commit
    commit: abc123…
    task_id: airline-001 # optional
    paper: https://arxiv.org/abs/…  # optional
  parity:
    claims: [protocol, scoring]
    known_gaps: []
```

| Rule | Detail |
| --- | --- |
| Location | `bora.yaml` (suite default) and/or member `task.yaml` |
| Override | task block **replaces** database block entirely |
| `original` | may omit `upstream` |
| `port` / `reimplementation` / `wrapper` | require `upstream.url` + (`ref` or `commit`) |
| Lock | enters digest + `bora lock` summary + evidence `lock.json` when written |

Author checklist: for ports, fill provenance before claiming upstream fidelity.

## Executors (`agent_profiles[].executor`)

**Authoritative discovery (do not hardcode):**

```bash
uv run bora executors      # .supported + host readiness
uv run bora executors -v   # + tools/session/stream; .acp_entries[] for ACP
```

- **`.supported`**: kinds valid for yaml `executor:` (this BORA install).
- **Coding agents (ACP Target):** `executor: acp` + `- plugin: acp` / `options.entry`.
- **HTTP agents:** e.g. `executor: openai-http` (+ optional `base_url` / `api_key` locator).
- Unknown kind fails at lock (`unsupported_capability`).
- Private CLI kinds (`codex` / `pi` / `opencode` / `claude-code` as **executor**) are **removed**; use ACP entry ids instead.

### ACP profiles

```yaml
# Database profiles.yaml
bindings:
  solver:
    executor: acp
    overlays:                     # optional plaza published set
      - overlays/AGENTS.md
    extensions:
      - plugin: acp
        options:
          entry: codex                # registry entry_id
    model: entry-default          # or a model the entry accepts
  pi-solver:
    executor: acp
    extensions:
      - plugin: acp
        options:
          entry: pi
          reasoning_effort: high      # optional; exact advertised thinking value
    model: zai-coding-cn/glm-5.2
    api_key: ${glm_coding_api_key}   # host env locator name only
```

| Field | Rule |
| --- | --- |
| `- plugin: acp` / `options.entry` | **Required** when `executor: acp`. Registry ids (discover via `bora executors -v` → `acp_entries`): typically `codex`, `claude-code`, `pi`, `opencode`, `grok-build`. |
| `overlays` | Optional list of paths starting with `overlays/`. Hub published set for that role. With `agent_ref`, resolve from the Agent package; otherwise Database-relative. Not inferred from plugin `src`. |
| `options.reasoning_effort` | Optional. Entries that advertise an ACP thinking selector (`category: thought_level` or a known id) bind after model via `set_config_option`. `grok-build` does not speak that method: the plugin adds `--reasoning-effort` to `grok agent … stdio` and records the selected `_meta` row. Exact value match; missing selector or unknown value fail closed. Unset does not fail. |
| `options.command` / `version` / `install_command` / … | **Forbidden** in package yaml (registry owns pins). |
| Host readiness | Per-entry `engine_ready` + `acp_entry_ready` in inventory — not the same as yaml `executor` kind. |

## Allowlisted CLI overrides

Fixed: `/parameters/seed`, `/parameters/active_profile`.
Job binding: `/bindings/<role>/{model,executor,api_key,base_url}` and
`/bindings/<role>/options/<key>`.
**Not** overridable: `limits.*` (task contract).

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
    api_key: ${zhipu_coding_api_key}
```

Design: `docs/design/02-task-package-and-config.md`, `docs/design/05-runtime/agent-service.md`.
