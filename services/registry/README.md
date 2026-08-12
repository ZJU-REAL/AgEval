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

# Orgs (packages must belong to an org; results belong to the uploader)
uv run bora registry org-create my-lab --display-name "My Lab"
uv run bora registry org-list

uv run bora publish tests/fixtures/databases/publish-min --org my-lab
# Same version again conflicts (409) unless explicit replace (org owner):
# uv run bora publish … --org my-lab --replace
uv run bora registry list
uv run bora registry show 'test/publish-min@0.1.0'
uv run bora registry set-visibility 'test/publish-min@0.1.0' --visibility public
# uv run bora registry delete 'test/publish-min@0.1.0' --yes
uv run bora lock 'test/publish-min@0.1.0' --task hello

# After a local run produced .bora/runs/<run_id>/
uv run bora results upload <database> --run <run_id>
# uv run bora results upload … --run <run_id> --replace   # owner overwrite
uv run bora results get <run_id> --out /tmp/restored
uv run bora results list
uv run bora results set-visibility <run_id> --kind attempt --visibility public
# Share / unshare a private result (owner only)
uv run bora results share <run_id> --kind attempt --share-org my-lab
uv run bora results unshare <run_id> --kind attempt --share-org my-lab
# uv run bora results delete <run_id> --kind attempt --yes

# After a suite run produced .bora/suite-runs/<suite_run_id>/summary.json
uv run bora results upload-suite <database> --suite-run <suite_run_id> [--public] [--agent x] [--model y]
# Optional: also pack each task's Attempt tree (Hub can open Job detail)
uv run bora results upload-suite <database> --suite-run <suite_run_id> --with-attempts
# uv run bora results upload-suite … --suite-run <id> --replace
uv run bora results get-suite <suite_run_id> [--out /tmp/restored-suite]
uv run bora results list-suites [--database-id <id>]
# Suite delete keeps attempts by default; optional cascade:
# uv run bora results delete <suite_run_id> --kind suite --yes
# uv run bora results delete <suite_run_id> --kind suite --with-attempts --yes
# Local fallback (no registry process):
uv run bora results list-suites --local <database>
uv run bora results get-suite <suite_run_id> --local <database>

# Suite task_refs get has_attempt_content when Attempt blobs exist and are visible.
# Hub Jobs: clickable when true; grey "Not uploaded" otherwise.

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

### CORS (Hub SPA)

Set `BORA_REGISTRY_CORS_ORIGIN` (default `*` when unset) so a browser Hub on
another origin can call `/v1/*` with `Authorization`. Local Hub dev usually
proxies via Vite (`apps/hub`) and does not need CORS.

### Package files API (Hub S2 / #38)

Browse published package contents **without** downloading the whole tar to the browser:

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/v1/packages/{id}/by-digest/{dig}/files` | same as package get |
| GET | `/v1/packages/{id}/by-digest/{dig}/files/{path}` | same |
| GET | `/v1/packages/{id}/versions/{ver}/files` | resolves to digest |
| GET | `/v1/packages/{id}/versions/{ver}/files/{path}` | resolves to digest |

List/get package meta (`GET /v1/packages`, versions, by-digest) includes
`package_kind` (`database` | `plugin`, derived from media type). List accepts
optional `?package_kind=database|plugin` (Hub plugin marketplace).


- List JSON: `{ database_id, digest, version, items: [{path, type, size}, …] }`
- File JSON: `{ path, size, encoding: "utf-8"|"base64", content, truncated }`
- **Hard top:** single file default **2 MiB** (`MAX_FILE_BYTES`); larger → **413**
- Path rules: reject `..`, absolute paths, empty segments
- Private unauthorized → **404** (not 403)
- Server indexes tar on first access (process LRU by digest); does not change upload format

### Organizations + ACL (design #52)

| Surface | Ownership | Private read | Delete / set-visibility / replace |
| --- | --- | --- | --- |
| Package release | **org** (`org_id` required on publish) | org members (or `admin`) | **org owner** (or `admin`) |
| Attempt / suite result | **uploader** (`uploaded_by` server-set) | owner, share→org/user, or `admin` | **uploader** (or `admin`) |

Joining an org does **not** reveal private results until the owner shares them.
Publish may be done by any org **member**; destructive package ops require **owner**.

| Method | Path |
| --- | --- |
| POST/GET | `/v1/orgs` |
| GET | `/v1/orgs/{id}` |
| DELETE | `/v1/orgs/{id}` (dissolve; fails if packages remain) |
| POST | `/v1/orgs/join` body `{ "invite_key" }` |
| POST | `/v1/orgs/{id}/leave` |
| POST | `/v1/orgs/{id}/claim` |
| GET/POST | `/v1/orgs/{id}/members` |
| DELETE | `/v1/orgs/{id}/members/{user}` |
| GET/POST | `/v1/orgs/{id}/invite-keys` (owner; create returns `invite_key` **once**) |
| DELETE | `/v1/orgs/{id}/invite-keys/{key_id}` (revoke) |
| POST | `/v1/packages` (optional metadata `replace: true` → overwrite same version) |
| DELETE | `/v1/packages/{id}/versions/{ver}` (org owner) |
| PATCH | `/v1/packages/{id}/versions/{ver}` body `{ "visibility" }` |
| DELETE | `/v1/results/attempts/{run_id}` (uploader) |
| PATCH | `/v1/results/attempts/{run_id}` body `{ "visibility" }` |
| DELETE | `/v1/results/suites/{id}[?with_attempts=1]` (uploader; cascade optional) |
| PATCH | `/v1/results/suites/{id}` body `{ "visibility" }` |
| GET/POST/DELETE | `/v1/results/attempts\|suites/{id}/shares` |

**Replace policy:** same `database_id@version` / `run_id` / `suite_run_id` defaults
to **409 conflict**. Explicit `replace: true` (CLI `--replace`) deletes the prior
row then inserts: blob, digests, metrics/labels, and visibility from the new
upload. No silent overwrite.

**Blob GC:** meta (+ result shares) deleted first; blob object removed only when
no remaining row references that digest (packages / attempt / suite prefixes
separately).

**Invite keys:** store only `token_hash` + `token_prefix`. Redeem hashes the
submitted key; `max_uses` uses a conditional `UPDATE` so concurrent joins cannot
over-admit. Create returns full `invite_key` once; list/revoke never return it again.

### Attempt file browse

When Attempt archives exist for a suite (e.g. suite upload with `--with-attempts`,
or a later `results upload`), `task_refs[].has_attempt_content` is set only if
the caller may read that attempt. File paths follow the same rules as package
files (no `..`, 2 MiB cap, **413** when larger):

| Method | Path |
| --- | --- |
| GET | `/v1/results/attempts/{run_id}/files` |
| GET | `/v1/results/attempts/{run_id}/files/{path}` |

### Suite results API

| Method | Path | Scope |
| --- | --- | --- |
| POST | `/v1/results/suites` | `results:upload` (+ user identity); optional `replace` |
| GET | `/v1/results/suites` | public ∪ owner ∪ share hit ∪ `admin` |
| GET | `/v1/results/suites/{suite_run_id}` | same visibility rules as attempts |
| DELETE | `/v1/results/suites/{suite_run_id}` | uploader (or `admin`); `?with_attempts=1` cascades owned attempts |
| PATCH | `/v1/results/suites/{suite_run_id}` | uploader (or `admin`); `{ "visibility" }` |
| GET | `/v1/results/suites/{suite_run_id}/content` | same |

Row fields: `database_id`, `database_version`, `pass_rate`, `mean_score`, `metrics`,
`task_refs`, optional `agent_label` / `model_label`, `exit_code`, and optional
config-comparability projection (`config_fingerprint`, `config_homogeneous`,
`actors_summary`) written at suite-run time (#42) — **not** invented at upload.
**No suite-level PASS** is stored or accepted (client keys `pass` / `verdict` / `suite_pass` → 400).
Leaderboard (#40) should refuse comparable ranking when `config_homogeneous` is
false; missing fingerprint on legacy rows degrades to labels-only.

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
Visibility is only **`public` | `private`**. Packages require **`org_id`**; private package
read is **org member** (or `admin`). Result private read is owner / share / admin
(see Organizations + ACL above).

## GitHub OAuth

Create a **GitHub OAuth App** (Settings → Developer settings → OAuth Apps).

| Setting | Local Hub / CLI |
| --- | --- |
| Homepage URL | e.g. `http://127.0.0.1:8700/` (informational) |
| Authorization callback URL | **`http://127.0.0.1:5174/login/callback`** (and `http://localhost:5174/login/callback` if you use that host) |
| Enable Device Flow | **On** (required for CLI `bora login`) |

Put in `services/registry/.env` (gitignored):

- `BORA_GITHUB_CLIENT_ID` / `BORA_GITHUB_CLIENT_SECRET`
- `BORA_GITHUB_LOGIN_ALLOWLIST=yourlogin` (comma-separated; **required** — empty deny)
- optional `BORA_GITHUB_WEB_REDIRECT_URIS=…` for extra Hub callback origins

### CLI — Device Flow

```bash
export BORA_REGISTRY_URL=http://127.0.0.1:8700
uv run bora login
# Open https://github.com/login/device and enter the printed user code
```

Writes `~/.bora/credentials` (0600). On success, Registry also stores a **user profile**
snapshot (`login` / display name / avatar) for Hub members list.

### Hub SPA — browser OAuth (Authorization Code)

1. Registry: `POST /v1/auth/github/web/start` with Hub `redirect_uri`
2. Browser opens GitHub authorize → user clicks **Authorize**
3. GitHub redirects to Hub `/login/callback?code=&state=`
4. Hub: `POST /v1/auth/github/web/callback` → Registry API token in `localStorage`

No device user code on Hub. Restart Registry after changing OAuth env.

CI continues to use `BORA_REGISTRY_TOKEN` (bootstrap/admin) without a browser.
