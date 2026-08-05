# BORA Database Registry service

Standalone HTTP(S) JSON service for **Database whole-package** publish / get.
**Not** BORA Core. Local path workflows never require this process.

## Quick start (stdlib / zero Docker)

```bash
# from repo root
python -m services.registry.app --host 127.0.0.1 --port 8700 --data-dir .bora/registry-data
# stderr prints bootstrap token once — store in ~/.bora/credentials (mode 0600)

export BORA_REGISTRY_URL=http://127.0.0.1:8700
export BORA_REGISTRY_TOKEN=<token>

uv run bora publish tests/fixtures/databases/publish-min
# default private; use --public for public visibility

rm -rf .bora/cache
uv run bora lock 'test/publish-min@0.1.0' --task hello
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

Env overrides: `BORA_REGISTRY_URL`, `BORA_REGISTRY_TOKEN`. Never put tokens in lock/evidence.

## Digests

- **packageDigest**: sorted tree paths + per-file sha256 + outer sha256 (`src/bora/registry/digest.py`)
- **blobDigest**: sha256 of deterministic tar+gzip archive
- Media type: `application/vnd.bora.database.v1.tar+gzip`

## Compose probe (Postgres + RustFS)

```bash
docker compose -f services/registry/docker-compose.yml up -d
```

In-process MVP uses **SQLite + filesystem blob** so CI/unit tests need no Docker.
Postgres/RustFS compose is the production-shaped local stack (Constitution D6.10).

## Scopes

| Scope | Capability |
| --- | --- |
| `registry:publish` | POST /v1/packages |
| `read-private` | Read private releases |
| `admin` | All |

Private unauthorized reads return **404** (not 403).
