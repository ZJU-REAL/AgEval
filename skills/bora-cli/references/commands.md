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

- One foreground Attempt via production composition root **when** `--task` is set, `-k` defaults to 1, and no `--resume-suite`.
- Creates evidence under package `tasks/<id>/.bora/runs/...` unless overridden internally.
- `logs` is absolute path to Attempt evidence root when available (single-Attempt path).
- **Always-k** (`--n-attempts` / `-k`, integer ≥1): fixed k independent Attempts per task in scope.
  CLI/job only — not `task.yaml`, not `config_fingerprint`. Feeds `metrics.pass_at_k` / `pass_power_k`.
- **Suite**: omit `--task` → all members; also used as the job container when `k>1` or resume.
- **`--max-concurrent-tasks`**: speeds wall time only; does not change k or PASS.
- **`--resume-suite <suite_run_id>`**: skip finished `(task_id, attempt_index)`, append Attempts, recompute metrics.
- Suite artifacts: `.bora/suite-runs/<id>/summary.json`, `progress.json`.
- Per invocation (ACP path): `agent/invocations/<nnnn>-*/trajectory.jsonl` is **turn-level**
  (user + merged assistant/thought + terminal). Stream chunks are not the training default;
  see `docs/design/05-runtime/evidence.md`.
- Docker packages use L1 path when `provider.kind: docker` (ACP via parent client +
  `docker exec` placement for coding entries).
- Attempt `result.json` may include `phase_timing` (`prepare` / `run` / `evaluate` / `cleanup`).

## `bora evidence`

- Read-only export of **sealed** invocations.
- Refuses unsealed (running) metadata.
- Writes `manifest.json` with `schema: bora.trajectory.export/1` and `source_digests`.
- Does not change evaluation score.

## `bora campaign`

- Foreground serial matrix; allowlisted `/parameters/*` axes.
- Not full campaign admission/retry policy.

## Control surface

- `submit` / `status` / `cancel` operate on ControlStore records.
- **Suite jobs** (bare 8-hex id): `status` / `cancel` accept optional `--database`
  to read `progress.json` or write `cancel.requested` when ControlStore has no row.
- Suite cancel: stop scheduling new units; SIGTERM stored pid when present.

## Always-k vs campaign

- **Always-k** (`bora run -k`): repeat independent Attempts for pass@k samples.
- **Campaign** (`bora campaign --matrix`): sweep allowlisted parameters / bindings on one task.
- Do not treat matrix axes as `n_attempts`.

## `bora results upload-suite` (#60)

- POSTs suite summary + optional archive to Registry suite result row.
- **Before upload:** ensures `metrics.pass_at_k` / `pass_power_k` / `n_attempts` /
  `k_values` / `per_task` when recoverable from `attempts[]` or task `n`/`c`
  (Hub does **not** recompute live).
- Contract: `metrics.pass_at_k["<k>"] = { value, n_tasks, incomplete_tasks }` (k string keys).
- `task_refs` may carry `n`, `c`, `attempt_run_ids` for multi-attempt audit.
- **`--with-attempts`:** packs `.bora/runs/<run_id>/` for each id in
  `attempt_run_ids` (preferred) or primary `run_id`; missing dirs fail closed.
- **`--replace`:** owner overwrite of same `suite_run_id` (default remains 409);
  with `--with-attempts`, linked attempts also replace.
- Registry stores full `metrics` blob (no strip). pass@k is **not**
  `config_fingerprint` / job identity.
- Hub Leaderboard: optional n_attempts / pass@k / pass^k columns when present;
  default sort remains pass_rate → mean_score.

## Registry owner ops

| Command | Who | Notes |
| --- | --- | --- |
| `bora results delete --kind attempt\|suite --yes` | `uploaded_by` (or admin) | Suite default does **not** delete attempts; `--with-attempts` cascades owned attempts |
| `bora results set-visibility --kind … --visibility public\|private` | uploader | After create; no re-upload required |
| `bora results unshare` | uploader | Same targeting as `share` (`--share-org` / `--share-user`) |
| `bora results upload\|upload-suite --replace` | uploader | Replaces blob + metrics/labels + visibility |
| `bora registry delete <id@ver> --yes` | **org owner** (or admin) | Meta + unreferenced package blob GC |
| `bora registry set-visibility <id@ver> --visibility …` | org owner | Flip without new version |
| `bora publish --replace` | org owner for overwrite | First publish still any org **member** |

Destructive CLI requires explicit `--yes`. Unauthorized private targets → **404**
fail-closed (no existence leak beyond existing list rules).
