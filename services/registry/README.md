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

Result archives keep layout `.bora/runs/<run_id>/…` so download extracts into a
browsable tree.

## Scopes

| Scope | Capability |
| --- | --- |
| `registry:publish` | POST /v1/packages; list private packages |
| `read-private` | Read private package releases |
| `results:upload` | POST /v1/results/attempts |
| `results:read` | Read private attempt results |
| `admin` | All |

`bora login` issues tokens with publish + read-private + results scopes.
Private unauthorized reads return **404** (not 403).
Visibility is only **`public` | `private`** (no org in this MVP).

## GitHub OAuth (Device Flow)

1. Create a GitHub OAuth App; enable **Device Flow**.
2. Put `BORA_GITHUB_CLIENT_ID` and `BORA_GITHUB_CLIENT_SECRET` in
   `services/registry/.env` (gitignored).
3. `bora login` → open verification URI → enter user code → credentials written.

CI continues to use `BORA_REGISTRY_TOKEN` without a browser.
