# CLI command notes

## `bora executors`

Two facts only (no version-gate / residual labels):

1. **What BORA supports** — adapters shipped or discovered on this install
2. **What the host can run** — CLI binary present on PATH (`shutil.which`)

Stdout JSON:

| Key | Meaning |
| --- | --- |
| `supported` | Kind names valid for `agent_profiles[].executor` (product surface) |
| `host_ready` | Subset ready on this machine (CLI on PATH, or api-client) |
| `missing_binary` | CLI kinds whose binary is **not** on PATH |
| `executors[]` | Per kind: `execution_mode`, `binary`, `binary_on_path`, `binary_path`, `host_ready` |

- Logic: `bora.adapters.executor_inventory` (CLI is thin print)
- Probe: `shutil.which` — works on macOS / Linux / Windows (`PATHEXT` → `.exe` etc.)
- `cli-process`: `binary_on_path` true/false; `host_ready` follows that
- `api-client` (e.g. `openai-http`): no binary; `binary_on_path` is null; `host_ready` true
- `-v` adds tools/session/stream + `credential_env_names` (adapter default env *names* only; not secrets)
- No package path; no secrets; exit 0

## `bora lock`

- Deterministic JSON on stdout (digest, task_id, resolution, resolved_references).
- No secret values.
- Does not create Run/Attempt or start Agent.

## `bora run`

- One foreground Attempt via production composition root.
- Creates evidence under package `.bora/runs/...` unless overridden internally.
- `logs` is absolute path to Attempt evidence root when available.
- Per invocation (ACP path): `agent/invocations/<nnnn>-*/trajectory.jsonl` is **turn-level**
  (user + merged assistant/thought + terminal). Stream chunks are not the training default;
  see `docs/design/05-runtime-core.md` §8.9.4a.
- Docker packages use L1 path when `provider.kind: docker`.

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
