# CLI command notes

## `bora executors`

Two product facts (+ ACP entry inventory):

1. **What BORA supports** — `agent_profiles[].executor` kinds on this install
2. **What the host can run** — binaries / ACP entries ready (no secrets)

Stdout JSON (high level):

| Key | Meaning |
| --- | --- |
| `supported` | Kind names valid for `agent_profiles[].executor` (e.g. `acp`, `openai-http`) |
| `host_ready` | Subset of kinds ready on this machine |
| `missing_binary` | Legacy CLI kinds missing PATH binary (ACP uses per-entry fields) |
| `executors[]` | Per kind: `execution_mode`, readiness, capability fields |
| `acp_entries[]` | Per ACP `entry_id`: `acp_command`, `engine_ready`, `acp_entry_ready`, `host_ready`, credential env *names* |

- Logic: `bora.adapters.executor_inventory` (CLI is thin print)
- ACP registry: `bora.adapters.acp_registry` (static pins; not package-overridable)
- `-v` adds tools/session/stream + richer entry fields
- No package path; no secrets; exit 0

**Author packages with:** `executor: acp` + `options.entry: <entry_id from acp_entries>`.

## `bora lock`

- Deterministic JSON on stdout (digest, task_id, resolution, resolved_references).
- No secret values.
- Does not create Run/Attempt or start Agent.
- Rejects unknown `executor` kinds and ACP profiles missing `options.entry`.

## `bora run`

- One foreground Attempt via production composition root.
- Creates evidence under package `.bora/runs/...` unless overridden internally.
- `logs` is absolute path to Attempt evidence root when available.
- Per invocation (ACP path): `agent/invocations/<nnnn>-*/trajectory.jsonl` is **turn-level**
  (user + merged assistant/thought + terminal). Stream chunks are not the training default;
  see `docs/design/05-runtime-core.md` §8.9.4a.
- Docker packages use L1 path when `provider.kind: docker` (ACP via parent client +
  `docker exec` placement for coding entries).

## `bora evidence`

- Read-only export of **sealed** invocations.
- Refuses unsealed (running) metadata.
- Writes `manifest.json` with `schema: bora.trajectory.export/1` and `source_digests`.
- Does not change evaluation score.

## `bora campaign`

- Foreground serial matrix; allowlisted `/parameters/*` axes.
- Not full campaign admission/retry policy.

## Control surface

- `submit` / `status` / `cancel` operate on ControlStore records (sketch maturity).
