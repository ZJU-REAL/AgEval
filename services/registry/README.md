# BORA Database Registry service

Standalone HTTP(S) JSON service for **Database package** publish/get/list and
**Attempt result** upload/get. **Not** BORA Core. Local path workflows never
require this process.

## Quick start (compose: Postgres + RustFS)

```bash
# from repo root
docker compose -f services/registry/docker-compose.yml up -d

# optional: copy and fill secrets
cp services/registry/.env.example services/registry/.env
# set BORA_GITHUB_CLIENT_ID / BORA_GITHUB_CLIENT_SECRET for bora login

uv sync --extra registry
uv run --extra registry python -m services.registry.app --host 127.0.0.1 --port 8700
# stderr prints bootstrap token once — or use bora login after OAuth is configured
```

When `BORA_REGISTRY_DATABASE_URL` and `BORA_REGISTRY_S3_ENDPOINT` are set (via
`.env` or the environment), the service uses **Postgres + S3**. Otherwise it
falls back to SQLite + filesystem under `--data-dir`.

## Zero-dep / tests

```bash
python -m services.registry.app --local --host 127.0.0.1 --port 8700
# or --memory-blob for tests
```

## CLI

```bash
export BORA_REGISTRY_URL=http://127.0.0.1:8700

# Interactive (GitHub Device Flow) — writes ~/.bora/credentials (0600)
uv run bora login

# CI / bootstrap
export BORA_REGISTRY_TOKEN=<token>

uv run bora publish tests/fixtures/databases/publish-min
uv run bora registry list
uv run bora registry show 'test/publish-min@0.1.0'
uv run bora lock 'test/publish-min@0.1.0' --task hello

# After a local run produced .bora/runs/<run_id>/
uv run bora results upload <database> --run <run_id>
uv run bora results get <run_id> --out /tmp/restored
uv run bora results list

# After a suite run produced .bora/suite-runs/<suite_run_id>/summary.json
uv run bora results upload-suite <database> --suite-run <suite_run_id> [--public] [--agent x] [--model y]
uv run bora results get-suite <suite_run_id> [--out /tmp/restored-suite]
uv run bora results list-suites [--database-id <id>]
# Local fallback (no registry process):
uv run bora results list-suites --local <database>
uv run bora results get-suite <suite_run_id> --local <database>

uv run bora cache list
uv run bora cache purge all --yes
```

## Credentials file

`~/.bora/credentials` (0600):

```json
{
  "registry": {
    "url": "http://127.0.0.1:8700",
    "token": "…"
  }
}
```

Env overrides: `BORA_REGISTRY_URL`, `BORA_REGISTRY_TOKEN`, optional
`BORA_RESULTS_URL`. Never put tokens in lock/evidence.

## Digests / media types

| Kind | Digest | Media type |
| --- | --- | --- |
| Database package | packageDigest + blobDigest | `application/vnd.bora.database.v1.tar+gzip` |
| Attempt result | blobDigest of archive | `application/vnd.bora.attempt-result.v1.tar+gzip` |
| Suite/job result | blobDigest of suite-run tree | `application/vnd.bora.suite-result.v1.tar+gzip` |

### Suite results API

| Method | Path | Scope |
| --- | --- | --- |
| POST | `/v1/results/suites` | `results:upload` |
| GET | `/v1/results/suites` | public items; private needs `results:read` / `admin` |
| GET | `/v1/results/suites/{suite_run_id}` | same visibility rules as attempts |
| GET | `/v1/results/suites/{suite_run_id}/content` | same |

Row fields: `database_id`, `database_version`, `pass_rate`, `mean_score`, `metrics`,
`task_refs`, optional `agent_label` / `model_label`, `exit_code`.  
**No suite-level PASS** is stored or accepted (client keys `pass` / `verdict` / `suite_pass` → 400).

Result archives keep layout `.bora/runs/<run_id>/…` so download extracts into a
browsable tree.

## Scopes

| Scope | Capability |
| --- | --- |
| `registry:publish` | POST /v1/packages; also list/get private packages |
| `read-private` | List/get private package releases |
| `results:upload` | POST /v1/results/attempts only (**not** private read) |
| `results:read` | List/get private attempt results |
| `admin` | All |

`bora login` issues tokens with publish + read-private + results upload/read.
Scopes are independent: upload-only tokens cannot list private results.
Private unauthorized reads return **404** (not 403).
Visibility is only **`public` | `private`** (no org in this MVP).

## GitHub OAuth (Device Flow)

1. Create a GitHub OAuth App; enable **Device Flow**.
2. Put in `services/registry/.env` (gitignored):
   - `BORA_GITHUB_CLIENT_ID` / `BORA_GITHUB_CLIENT_SECRET`
   - `BORA_GITHUB_LOGIN_ALLOWLIST=yourlogin` (comma-separated; **required** — empty deny)
3. `bora login` → open verification URI → enter user code → credentials written.

CI continues to use `BORA_REGISTRY_TOKEN` (bootstrap/admin) without a browser.
