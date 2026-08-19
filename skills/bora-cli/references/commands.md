# CLI command notes

## `bora executors`

Two product facts (+ ACP entry inventory):

1. **What BORA supports** — `agent_profiles[].executor` kinds on this install
2. **What the host can run** — binaries / ACP entries ready (no secrets)

Stdout JSON (high level):

| Key | Meaning |
| --- | --- |
| `supported` | Kind names valid for `agent_profiles[].executor` (e.g. `acp`, `openai-http`) |
| `host_ready` | Subset of kinds whose **L0 host SPI** can be constructed here |
| `missing_binary` | Legacy CLI kinds missing PATH binary (ACP uses per-entry fields) |
| `executors[]` | Per kind: `execution_mode` (from `describe()` when published), L0 `host_ready`, plugin `l1_bake_declared` |
| `acp_entries[]` | Per ACP `entry_id`: `acp_command`, `engine_ready`, `acp_entry_ready`, `host_ready`, credential env *names* |

- Logic: `bora.adapters.executor_inventory` (CLI is thin print)
- ACP registry: `bora.plugins.contrib.acp.registry` (static pins; not package-overridable)
- Plugin `host_ready` uses declared `host_requires` / reachable `describe()` — not “installed” and not PATH-probing wheel binaries
- `-v` adds tools/session/stream + richer entry fields
- L0 ACP spawn env is `project_cli_child_env` (allowlist only: core keys +
  entry credential names + binding locators + `fixed_env`). Undeclared host
  tokens do not reach the entry. `HOME` is still projected.
- No package path; no secrets; exit 0

**Author packages with:** `executor: acp` + `- plugin: acp` / `options.entry: <entry_id from acp_entries>`.

## `bora lock`

- Deterministic JSON on stdout (digest, task_id, resolution, resolved_references).
- No secret values.
- Does not create Run/Attempt or start Agent.
- Rejects unknown `executor` kinds and ACP profiles missing `- plugin: acp` / `options.entry`.
- `--probe`: same lock plus observational `probe` (path, ready, checks). Does not
  change the digest. Exit 1 when the **selected** `provider.kind` path is unsatisfied.
  L0 runs declared `host_requires`; L1 checks bake file + Docker daemon + locator
  **names** (never values). `BORA_OFFLINE_AGENT=1` is reported; probe still does not spawn.

## `bora run`

- `--probe` (with or without `--task`): same feasibility report as `lock --probe`;
  does not start an Attempt. Omit `--task` to probe every member.
- One foreground Attempt via production composition root **when** `--task` is set, `-k` defaults to 1, and no `--resume-suite`.
- Evidence under Dataset root `.bora/runs/<run_id>/` (Hub-facing curated tree).
- `logs` / `evidence_path` are portable relative to the Dataset root (e.g. `.bora/runs/<run_id>`);
  readers still accept legacy host absolute paths.
- **Always-k** (`--n-attempts` / `-k`, integer ≥1): fixed k independent Attempts per task in scope.
  CLI/job only — not `task.yaml`, not `config_fingerprint`. Feeds `metrics.pass_at_k` / `pass_power_k`.
- **Suite**: omit `--task` → all members; also used as the job container when `k>1` or resume.
- **`--max-concurrent-tasks`**: speeds wall time only; does not change k or PASS.
- **`--resume-suite <suite_run_id>`**: skip finished `(task_id, attempt_index)`
  (PASS/FAIL/**ERROR** all count as finished), append missing Attempts, recompute
  metrics. Cancel placeholders are retried.
- **`--replace-slot`** (with `--resume-suite` and `--task`): re-run that finished
  slot even if PASS / FAIL / ERROR. Writes a new `run_id`; old current moves to
  `previous[]`. Always-k uses `--attempt-index` (default 0). Same
  `config_fingerprint` required. In-progress / `cancel.requested` refuse.
- **`--keep-workspace`** (L1 / `provider.kind: docker` only): retain host
  `.bora/runs/<run_id>/l1-work/` after cleanup for local debug. **Default off** —
  Runtime deletes `l1-work` after container cleanup. Docker volumes and env
  containers are still removed. Not required for Hub; upload pack excludes
  `l1-work/**` even if residual remains.
- Suite artifacts: `.bora/suite-runs/<id>/summary.json`, `progress.json`.
- Per invocation (any executor): Core writes `agent/invocations/<nnnn>-*/trajectory.jsonl`
  from `bora.trajectory.event/1` in ReAct file order (user → thought/tool/observation
  bursts → final assistant → terminal). Rows use `session_id` and producer `source`
  (not `acp_session_id`). Thought / `tool_call` / `observation` / final assistant may
  carry observational `elapsed_ms` when the adapter had timing; missing values are
  omitted. Stream chunks are not the training default; see
  `docs/design/05-runtime/evidence.md`.
- Docker packages use L1 path when `provider.kind: docker`. First-party coding entries
  stay on the parent ACP client + `docker exec` placement; other installed executors
  bind via `bind_to_target`.
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

## `bora results upload` (single Attempt)

- Archives one `.bora/runs/<run_id>/` as an **Attempt** result row.
- Useful for archival / known deep-link URLs.
- **Does not create a suite Leaderboard row.** Hub Dataset Leaderboard and Task →
  Jobs are driven by **suite** list APIs. Prefer `upload-suite` when the operator
  goal is “see it on Hub”.

## `bora results upload-suite`

- POSTs suite summary + optional archive to Registry **suite** result row.
- **Prerequisite:** a suite job under `.bora/suite-runs/<suite_run_id>/` from
  `bora run <database>` **without** `--task` (or Always-k / resume that wrote a suite).
- **Before upload:** ensures `metrics.pass_at_k` / `pass_power_k` / `n_attempts` /
  `k_values` / `per_task` when recoverable from `attempts[]` or task `n`/`c`
  (Hub does **not** recompute live).
- Contract: `metrics.pass_at_k["<k>"] = { value, n_tasks, incomplete_tasks }` (k string keys).
- `task_refs` may carry `n`, `c`, `attempt_run_ids`, and `previous[]` (superseded current).
- **`--with-attempts`:** packs `.bora/runs/<run_id>/` for each id in
  `attempt_run_ids` (preferred) or primary `run_id`; missing dirs fail closed.
  Sets `task_refs[].has_attempt_content` so Hub Task Jobs can open Attempt detail.
- **`--agent` / `--model`:** optional Leaderboard labels (else derived from suite summary).
- **`--replace`:** owner overwrite of same `suite_run_id` (default remains 409);
  with `--with-attempts`, linked attempts also replace. **No** `previous[]`.
- **`--task` / `--run`:** append one local slot onto an already-uploaded suite
  (upload the new Attempt, then PATCH current + `previous[]`). Must not combine
  with `--replace`.
- Registry stores full `metrics` blob (no strip). pass@k is **not**
  `config_fingerprint` / job identity.
- Hub Leaderboard: **Public** lists **complete, release-bound suite** rows (`board=1`); optional
  n_attempts / pass@k / pass^k when present; default sort remains pass_rate → mean_score.
  Incomplete or draft-bound suites appear on Leaderboard **Internal** (same table) and Task Jobs.

### Hub path checklist

```text
bora publish <db> --org <org> --draft
bora release <org/dataset>            # or bora publish … without --draft
bora run <db> [--profiles …]          # omit --task → suite
  → .bora/suite-runs/<8-hex>/summary.json
bora results upload-suite <db> --suite-run <8-hex> --public [--with-attempts]
  → Hub: Dataset → Leaderboard row (complete + release-bound);
    Task → Jobs → optional Attempt deep-link (all visible suites)
```

## `bora publish` / `bora release`

- `bora publish <db> --org <org> --draft` overwrites the one draft slot for that
  `database_id`. Reserved version name `draft` is not a release.
- `bora release <database_id>` (owner) promotes the current draft to an immutable
  `database_id@version`. `--version` overrides the draft `bora.yaml` version.
- Direct `bora publish` without `--draft` still creates a release.
- Plugin packages do **not** use the draft slot.
- Unauthorized readers get 404 on draft; they never see whether a draft exists.

## `bora view`

- Local Database UI. No Registry. Jobs row can delete a local Job after preview.
- `--dev`: API only; starts `apps/viewer` Vite when possible, else prints the
  two-process fallback. Advertise `:5173` only after Vite is listening.
- `--open /jobs/<id>` (or a task/run path) deep-links after a local run.
- Jobs list includes suite runs **and** single-task Attempts in the opened Database.

## `bora jobs delete`

- Same use case as Viewer Job delete. **Not** `bora results delete` (Registry).
- `--local <database>` `--job <id>`: `id` is a suite_run_id or an **unclaimed**
  single `run_id`.
- Without `--yes`: print preview JSON (paths, bytes, cascade run ids) and exit 2.
- With `--yes`: hard-delete those trees. Suite delete always cascades referenced
  Attempts; they must not reappear as singles.
- Refuses: inner Attempt still claimed by a suite; in-progress suite /
  live `cancel.requested`; path escape; Attempt claimed by another remaining suite.

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
