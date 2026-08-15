---
name: bora-cli
description: >
  Operate BORA public CLI (bora lock/run/plugin/view/publish/release/executors/campaign/evidence/status/submit/cancel):
  install with uv, command flags, allowlisted --set pointers, exit codes, Result.logs
  trajectory locator, offline fail-closed (BORA_OFFLINE_AGENT), list supported executor
  kinds and ACP entry readiness, plugin install/list/uninstall, dataset draft/release,
  and which example packages to run. Use when the agent must lock a package, run an
  Attempt, list executor / entry values, install a bora.plugin/1, open local Jobs,
  export trajectory, upload suite results for Hub, interpret PASS/FAIL/ERROR, debug
  CLI output, or choose a public smoke. Trigger phrases: "bora run", "bora lock",
  "bora plugin", "bora view", "bora publish", "bora release", "bora executors",
  "upload-suite", "Hub Leaderboard", "which executor", "ACP entry", "export trajectory",
  "Result.logs", "exit code", "offline agent", "switch profile", "install nooa",
  "draft slot".
  Do not invent flags not in production.
---

# BORA CLI

## Install

From repo root:

```bash
uv sync --frozen --all-packages
uv run bora --help
```

## Commands (shipped)

| Command                                                       | Use for                                                                                            |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `bora executors`                                              | Supported `executor:` kinds + host readiness; ACP entry probe (JSON)                               |
| `bora executors -v` / `--verbose`                             | Same + tools/session + default credential env _names_ + entry detail                               |
| `bora plugin install\|list\|uninstall`                        | Local mechanism plugins (`bora.plugin/1`); **never** rewrites profiles                             |
| `bora plugin publish`                                         | Upload plugin package (`package_kind=plugin`) to Registry                                          |
| `bora -V` / `bora --version`                                  | Package version (`-V`; keep `-v` free for verbose)                                                 |
| `bora lock <package> --task <id>`                             | Config lock summary (no Agent); includes `job_overlay`                                             |
| `bora lock\|run … --probe`                                    | Host vs L1 feasibility for this binding/`provider.kind`; no Agent, no bake                         |
| `bora lock ... --set /parameters/seed=7`                      | Allowlisted override                                                                               |
| `bora lock/run ... --profiles path/to/profiles.yaml`          | Alternate job binding file (replaces Database `profiles.yaml`)                                     |
| `bora run <package> --task <id>`                              | One foreground Attempt                                                                             |
| `bora run <package> [-k N] [--max-concurrent-tasks N]`        | Suite / Always-k job (`-k` = `--n-attempts`; CLI only)                                             |
| `bora run … --resume-suite <id> [--task id] -k N`             | Append Attempts into existing suite job; recompute pass@k / pass^k                                 |
| `bora run … --keep-workspace`                                 | L1 only: retain host `l1-work/` after cleanup (default: delete; Docker volumes still go)           |
| `bora run ... --set '/bindings/solver/options/entry="pi"'`    | Job binding override (entry/model)                                                                 |
| `bora campaign <package> --task <id> --matrix ...`            | Serial matrix (`/parameters/*` or `/bindings/<role>/…`); ≠ Always-k                                |
| `bora evidence <logs-path> --out <dir>`                       | Sealed trajectory export (no score change)                                                         |
| `bora results upload-suite …`                                 | Suite aggregates → Registry; recompute pass@k if missing; job_overlay                              |
| `bora results upload-suite … --with-attempts`                 | Also upload attempt dirs from task_refs.attempt_run_ids / run_id                                   |
| `bora results upload\|upload-suite … --replace`               | Owner overwrite same run_id / suite_run_id (default 409)                                           |
| `bora results delete\|set-visibility … --kind attempt\|suite` | Owner delete (`--yes`) or flip visibility after upload                                             |
| `bora results share\|unshare …`                               | Grant / revoke private result access (owner only)                                                  |
| `bora results export-profiles <suite_run_id> --out …`         | Rehydrate job binding as profiles.yaml (locators only)                                             |
| `bora view <database> [--dev] [--open …]`                     | Local Jobs UI (no Registry). `--dev` starts Vite when possible; `--open` deep-links a job/task/run |
| `bora jobs delete --local <db> --job <id> --yes`              | Delete a local Job tree (suite always cascades Attempts). Preview without `--yes`; not Registry |
| `bora publish … --org … [--draft] [--replace]`                | Package publish; `--draft` overwrites the draft slot; `--replace` is org-owner only                |
| `bora release <database_id>`                                  | Owner: promote the current dataset draft to an immutable version                                   |
| `bora registry delete\|set-visibility <id@ver>`               | Org-owner package delete (`--yes`) / visibility flip                                               |
| `bora registry org-create\|org-list`                          | Create / list orgs. Allowlisted official slugs (default `official`) need admin bootstrap token     |
| `bora registry org-add-member\|org-remove-member`             | Owner or admin add / remove members by GitHub login; target need not be logged in                |
| `bora registry org-set-role\|org-transfer`                    | Change an existing member's role, or hand the org to a current member (caller becomes member)    |
| `bora submit` / `bora status` / `bora cancel`                 | Durable Run **or suite job** (8-hex id; status/cancel may take `--database`)                       |

Discover flags with `uv run bora <cmd> --help`. Source of truth: `src/bora/cli/main.py`.

### Which `executor:` / ACP `entry` values?

```bash
uv run bora executors
uv run bora executors -v
# .supported     = agent_profiles[].executor values (e.g. acp, openai-http)
# .acp_entries   = options.entry ids + engine/acp binary readiness
# .host_ready    = L0 host SPI constructable (declared host_requires / describe())
# .executors[].l1_bake_declared = image_contribute + Dockerfile.bake (plugins)
# .missing_binary = (legacy CLI kinds only; ACP uses per-entry readiness)
# Note: package version is `bora -V` / `--version` (not `-v`).
```

Coding-agent packages use:

```yaml
executor: acp
options:
  entry: opencode # or codex | claude-code | pi | grok-build | …
```

Do **not** hardcode a fixed list; inventory is authoritative. Do **not** use
`executor: codex|pi|opencode|claude-code` (migrated to ACP entry).

Installed plugins (e.g. `nooa`, `dsh`) appear as additional `executor:` values after
`bora plugin install` — still selected only via profiles / `--set` bindings.

### Plugin install (local cache only)

```bash
uv run bora plugin install plugins/nooa
uv run bora plugin list
# Bind with profiles — install never edits task.yaml / profiles.yaml
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.nooa.yaml
```

Cache root: `$BORA_HOME/plugins` (default `~/.bora/plugins`).  
**Recognition** (list/lock) ≠ **L0 host-ready** (`host_requires`) ≠ **L1 bake-declared** (`image_contribute` bake).
Writing a new plugin package is `$bora-plugin`, not this skill.

## Allowlisted `--set` pointers

Fixed parameter leaves (see Config Core):

- `/parameters/seed`
- `/parameters/active_profile`

Job binding axes:

- `/bindings/<role_id>/model`
- `/bindings/<role_id>/executor`
- `/bindings/<role_id>/api_key`
- `/bindings/<role_id>/base_url`
- `/bindings/<role_id>/options/<key>` (plugin-opaque; ACP denylist still rejects `command` / engine keys)

**Not** overridable: intent `limits.*` (task contract).

Value after `=` is JSON (strings need quotes):  
`--set '/bindings/solver/options/entry="pi"'` · `--set '/parameters/active_profile="solver"'`.

## Exit codes

| Code | Meaning                  |
| ---- | ------------------------ |
| `0`  | PASS; or `--probe` ready |
| `1`  | FAIL (evaluator); or `--probe` selected path unsatisfied |
| `2`  | ERROR / config / runtime |

## Interpret `bora run` JSON

**Single Attempt** (`--task` and default `-k 1`, no resume): typical fields `status`, `score`, `assurance`, `agent_invocations`, `evidence_path`, **`logs`** (portable under Dataset root, e.g. `.bora/runs/<run_id>`).

- On disk: `<dataset>/.bora/runs/<run_id>/` — Hub-facing curated evidence (`result.json`, `agent/`, `evaluation/`, `artifacts/`, lock/runtime JSON).
- L1 host sandbox lives at `l1-work/` **during** the Attempt; **default cleanup deletes it**. Use `--keep-workspace` only for local debug. `bora results upload` never packs `l1-work/**`.
- Inspect trajectory: open `<dataset>/.bora/runs/<run_id>/agent/invocations/<nnnn>-*/trajectory.jsonl` (**turn-level** training rows) and `events.jsonl` (optional stream/debug)
- Export: `uv run bora evidence <dataset>/.bora/runs/<run_id> --out /tmp/bora-export`
- Trajectory presence **never** upgrades score

**Suite / Always-k** (omit `--task`, or `-k` > 1, or `--resume-suite`): job under `<dataset>/.bora/suite-runs/<suite_run_id>/`.

| Path                         | Content                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------- |
| `summary.json` → `metrics`   | `pass_rate`, `mean_score`, `pass_at_k`, `pass_power_k`, `n_attempts`, `k_values`, `per_task` |
| `summary.json` → `task_refs` | May include `n`, `c`, `attempt_run_ids` (multi-attempt audit / upload)                       |
| `progress.json`              | Multi-unit progress                                                                          |
| Attempt `result.json`        | May include `phase_timing` (prepare/run/evaluate/cleanup)                                    |

- pass@k / pass^k are **job** metrics (mean over tasks); **not** package identity / fingerprint
- `pass_at_k["k"]` shape: `{ value, n_tasks, incomplete_tasks }` (k as string key)
- `upload-suite` **ensures/recomputes** k maps locally before POST; Registry stores full `metrics`
- Hub Leaderboard may show n_attempts / pass@k / pass^k when present (default sort still pass_rate)
- `n_attempts` is **CLI/job only** — never invent a `task.yaml` field
- Concurrency (`--max-concurrent-tasks`) only speeds scheduling

## Hub visibility (critical — suite vs attempt)

**Hub Dataset Leaderboard and Task → Jobs are suite-first.** They list Registry
**suite** rows (`GET /v1/results/suites`), not a feed of bare attempts.

| What you did                                                                           | Registry                                        | Hub Leaderboard / Task Jobs                                                                                                              |
| -------------------------------------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `bora run … --task X` then `bora results upload … --run <run_id>`                      | Attempt row exists (`suite_run_id` often empty) | **Usually invisible** as a leaderboard / Jobs row                                                                                        |
| `bora run <database>` (omit `--task`) → `bora results upload-suite … --suite-run <id>` | Suite row + metrics + task_refs                 | **Public Leaderboard** only if **complete** and bound to a **release**; **Internal** and Task Jobs list every visible suite (including incomplete / draft-bound) |
| `upload-suite … --with-attempts`                                                       | Also packs each attempt under task_refs         | Task Jobs can **deep-link** Attempt detail / trajectory                                                                                  |

**Do this when the goal is “show on Hub”:**

```bash
# 1) Suite job (all members). Use --profiles for job binding (agent×model axis).
uv run bora run examples/journeys --profiles path/to/profiles.yaml

# 2) suite_run_id is 8-hex in JSON / summary_path / .bora/suite-runs/<id>/
# 3) Upload suite (+ optional full Attempt evidence for Jobs deep-link)
uv run bora results upload-suite examples/journeys \
  --suite-run <suite_run_id> \
  --public \
  --with-attempts \
  --agent <label> \
  --model <label>
```

**Anti-pattern (common agent mistake):** only `bora results upload` after single-task runs, then “why doesn’t Hub show it?” — CLI `results list` may still show attempts; Hub SPA primary surfaces do **not** treat them as Leaderboard / Jobs rows.

Also:

- Hub must point at the **same** Registry URL as `~/.bora/credentials` (local dev often `http://127.0.0.1:8700` + Hub `VITE_REGISTRY_PROXY_TARGET`).
- `bora results upload` remains valid for archiving a single Attempt / deep-link when you already know `run_id`; it is **not** a substitute for `upload-suite` for Leaderboard.
- Public Leaderboard further requires a **complete** suite (every task on the bound version has a result; FAIL / ERROR still count) bound to a **release**. `bora publish --draft` then `bora release` (or a direct `bora publish` release) before expecting a board row. Draft-bound and incomplete suites stay on Jobs.
- Suite metrics (`pass_rate`, pass@k, …) are **observational** — not suite-level PASS.

## Offline / fail-closed

```bash
BORA_OFFLINE_AGENT=1 uv run bora run examples/core --task sdk-agent-session
```

Must not PASS agent packages. Typed errors only.

## Recommended smokes

| Goal                         | Command                                                                                                                                        |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| List executors / ACP entries | `uv run bora executors` / `uv run bora executors -v`                                                                                           |
| Package version              | `uv run bora -V` / `uv run bora --version`                                                                                                     |
| Lock only                    | `uv run bora lock examples/core --task config-minimal`                                                                                         |
| ACP multi-turn (host)        | `uv run bora run examples/core --task sdk-agent-session`                                                                                       |
| ACP entry switch             | `uv run bora run examples/core --task builtin-executor-conformance --set '/bindings/solver/options/entry="pi"'`                                |
| Trajectory                   | `uv run bora run examples/core --task attempt-trajectory`                                                                                      |
| Hard ceiling                 | `uv run bora run examples/core --task hard-ceiling-trajectory`                                                                                 |
| L1 SDK session               | `uv run bora run examples/l1 --task sdk-session-single-actor`                                                                                  |
| L1 isolation contracts       | Provider tests: `uv run pytest tests/provider_l1/test_harness_isolation_contracts.py tests/provider_l1/test_filtered_mount.py -q`              |
| nooa plugin (L1)             | `bora plugin install plugins/nooa` then `bora run examples/journeys --task terminal-jsonl-agg --profiles examples/journeys/profiles.nooa.yaml` |
| dsh plugin (L1)              | `bora plugin install plugins/dsh` then `bora run examples/journeys --task terminal-jsonl-agg --profiles examples/journeys/profiles.dsh.yaml`   |
| dsh file-effect policy       | same + `--profiles examples/journeys/profiles.dsh.read-only.yaml` or `--set '/bindings/solver/options/permission="read-only"'`                 |

## Detail

- Command semantics & Result fields: [references/commands.md](references/commands.md)
- Failure diagnosis: [references/failures.md](references/failures.md)
