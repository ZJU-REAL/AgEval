# BORA CLI

This package directory implements the public `bora` console script (`main.py`).  
The CLI only maps argv → application use cases → stdout / stderr / exit codes. It does **not** own Config merge, digests, or PASS.

Deeper diagnostics and Result fields: `skills/bora-cli/`.  
Registry service ops: `services/registry/README.md`.

## Install

From the repository root:

```bash
uv sync
uv run bora --help
# short form for help (standard):
uv run bora -h

# package version (capital -V; -v is often verbose on subcommands):
uv run bora -V
uv run bora --version

# when talking to a Postgres/S3-backed Registry process:
uv sync --extra registry
```

## Conventions

| Item | Meaning |
| --- | --- |
| Database path | Root with `bora.yaml` (`bora.database/1`) |
| Registry ref | `<database_id>@<version>` or `<database_id>@sha256:<64hex>` |
| `--task` | Member `task_id` under `tasks/<id>/task.yaml` |
| Success output | Most commands print **one JSON object** on stdout (`sort_keys`) |
| Failure | Human message on stderr + stable `error_code`; often exit **2** |
| Secrets | Never written into lock / evidence; Registry uses `~/.bora/credentials` or env |

### Global flags

| Flag | Meaning |
| --- | --- |
| `-h`, `--help` | Show help (root or any subcommand). **`-h`**, not `-H`, is the usual short form. |
| `-V`, `--version` | Print package version and exit. Capital **`-V`** avoids clashing with `-v` (verbose). |

### Exit codes (`bora run` / `campaign`)

| Code | Meaning |
| --- | --- |
| `0` | PASS |
| `1` | FAIL (evaluator) |
| `2` | ERROR / config / runtime |

Other subcommands: `0` on success, typically `2` on operator error.

### Common environment variables

| Variable | Role |
| --- | --- |
| `BORA_REGISTRY_URL` | Registry base URL |
| `BORA_REGISTRY_TOKEN` | Bearer token (CI; overrides file token) |
| `BORA_RESULTS_URL` | Results store URL (defaults to Registry URL) |
| `BORA_CACHE_ROOT` | Local verified cache root (default `.bora/cache`) |
| `BORA_OFFLINE_AGENT` | Set to `1` for fail-closed agent path (offline tests) |

Credentials file `~/.bora/credentials` (mode `0600`):

```json
{
  "registry": {
    "url": "http://127.0.0.1:8700",
    "token": "…"
  }
}
```

---

## Command map

| Command | Purpose |
| --- | --- |
| `bora tasks` | List member task ids in a Database |
| `bora lock` | Lock config (no Agent) |
| `bora run` | Run one member or a full suite |
| `bora campaign` | Serial parameter-matrix campaign |
| `bora executors` | Host executor / ACP entry inventory |
| `bora evidence` | Export sealed trajectory copy (does not change score) |
| `bora submit` / `status` / `cancel` | Durable Run control (v0.12 sketch) |
| `bora login` | GitHub **Device Flow** → write credentials (Hub uses browser OAuth instead) |
| `bora publish` | Publish a Database package (**requires `--org`**) |
| `bora registry list\|show` | Browse remote packages |
| `bora registry org-create\|org-list` | Create / list organizations (packages belong to orgs) |
| `bora cache list\|path\|purge` | Local verified cache |
| `bora results upload\|get\|list` | Attempt run evidence bundles |
| `bora results upload-suite\|get-suite\|list-suites` | Suite/job aggregates + task refs (no suite PASS) |
| `bora results share` | Share a private result with org(s) and/or user(s) |
| `bora view` | Local read-only Database Web UI (no Registry) |

Discover flags with `uv run bora <cmd> -h`.

---

## Local path workflow (no Registry)

```bash
uv run bora tasks examples/core

# Local Web UI: Jobs → Tasks → Trial (suite-runs under .bora/; no Registry)
uv run bora view examples/core
# uv run bora view tests/fixtures/databases/suite-min --port 8765 --no-browser

uv run bora lock examples/core --task config-minimal

uv run bora run examples/core --task sdk-agent-session

# Full suite (omit --task)
uv run bora run examples/core

# Allowlisted --set (JSON Pointer = JSON value)
uv run bora lock examples/core --task config-minimal --set /parameters/seed=7
uv run bora run examples/core --task sdk-agent-session \
  --set '/parameters/active_profile="pi-mini"'
```

### Allowlisted `--set` pointers

Only these Config Core pointers are accepted (others fail closed):

- `/parameters/seed`
- `/parameters/active_profile`
- `/limits/wall_time_seconds`
- `/limits/agent_invocations`
- `/limits/environment_actions`
- `/limits/memory_mb`

String values need JSON quotes, e.g. `--set '/parameters/active_profile="opencode-acp"'`.

### Evidence and trajectory

`bora run` JSON often includes **`logs`**: Attempt evidence root.

```bash
uv run bora evidence "$LOGS_PATH" --out /tmp/bora-export
```

Trajectory presence **≠** PASS. PASS comes only from an independent evaluator.

### Campaign / control plane (brief)

```bash
uv run bora campaign examples/core --task config-minimal \
  --matrix '/parameters/seed=[1,2,3]'

uv run bora submit examples/core --task config-minimal
uv run bora status <run_id>
uv run bora cancel <run_id>
```

### Executors

```bash
uv run bora executors      # JSON: supported / host_ready / acp_entries
uv run bora executors -v   # --verbose: credential env names and extra detail
```

Coding-agent packages use `executor: acp` + `options.entry: …`. Prefer inventory output over hardcoded vendor lists.

---

## Registry workflow (optional service)

```bash
docker compose -f services/registry/docker-compose.yml up -d
uv run --extra registry python -m services.registry.app
export BORA_REGISTRY_URL=http://127.0.0.1:8700
```

### Login, org, and publish

Packages **must** belong to an organization (`--org`). Results belong to the
uploader and can later be shared to an org or user.

```bash
# Interactive GitHub Device Flow (server needs BORA_GITHUB_* + LOGIN_ALLOWLIST)
uv run bora login

# CI: no browser
export BORA_REGISTRY_TOKEN=<bootstrap-or-ci-token>

uv run bora registry org-create my-lab --display-name "My Lab"
uv run bora registry org-list

# Default visibility private; explicit public. --org is required.
uv run bora publish tests/fixtures/databases/publish-min --org my-lab
uv run bora publish path/to/db --org my-lab --public
```

### Lock / run by ref

```bash
uv run bora lock 'test/publish-min@0.1.0' --task hello
uv run bora run  'test/publish-min@0.1.0' --task hello
uv run bora lock 'test/publish-min@sha256:…' --task hello
```

### Catalog and cache

```bash
uv run bora registry list
uv run bora registry list --prefix test/
uv run bora registry show 'test/publish-min@0.1.0'

uv run bora cache list
uv run bora cache path 'test/publish-min@sha256:…'
uv run bora cache purge all --yes   # destructive; requires --yes
```

### Attempt results

Upload sealed trees under `<database>/.bora/runs/<run_id>/` (not package releases).

```bash
uv run bora results upload /path/to/database --run <run_id>
uv run bora results list --database-id test/publish-min
uv run bora results get <run_id> --out /tmp/restored-run
# Share a private result (owner only):
uv run bora results share <run_id> --kind attempt --share-org my-lab
```

Visibility is **public** or **private** only. Packages are owned by an **org**;
results are owned by the **uploader** (`uploaded_by`). Private results stay
invisible to org members until the owner shares them. Default private; `--public`
for public.

### Suite / job results

After `bora run <database>` (full suite), summary lives at
`<database>/.bora/suite-runs/<suite_run_id>/summary.json` with observational
`metrics.pass_rate` / `metrics.mean_score` (not suite PASS).

```bash
uv run bora results upload-suite /path/to/database --suite-run <suite_run_id> \
  --agent codex --model gpt-test
uv run bora results list-suites --database-id test/suite-min
uv run bora results get-suite <suite_run_id> --out /tmp/restored-suite
# No registry: fall back to local suite-runs
uv run bora results list-suites --local /path/to/database
uv run bora results get-suite <suite_run_id> --local /path/to/database
```

---

## Suggested smokes

| Goal | Command |
| --- | --- |
| CLI works | `uv run bora -h` / `uv run bora -V` |
| List tasks | `uv run bora tasks examples/core` |
| Lock only | `uv run bora lock examples/core --task config-minimal` |
| Local agent | `uv run bora run examples/core --task sdk-agent-session` |
| Registry (service up) | `publish` → wipe `BORA_CACHE_ROOT` → `lock <ref> --task …` |

Example packages and evidence grades: `examples/README.md`, root `Agents.md`.

---

## Implementation boundary

| Layer | Owns |
| --- | --- |
| `cli/main.py` | Typer routes, JSON printing, exit codes |
| `application/*` | Use cases (lock / run / publish / login / …) |
| Config / Core | Spec load, lifecycle, PASS |
| `services/registry` | Standalone HTTP service; CLI is HTTP client only |

New commands: thin wrapper in `main.py`, logic in `application/`, update this README and `skills/bora-cli` when the public surface changes.
