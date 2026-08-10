# BORA Hub (`apps/hub`)

Registry **Dataset catalog** SPA: list packages, open README and tasks, preview
files, browse Task Jobs, and Leaderboard.

Also covers **organizations** (members, org packages, shared suite results,
invite keys, leave / dissolve), **GitHub browser login**, and opening a Job’s
run detail when the corresponding Attempt artifacts were uploaded.

**Not** the local results viewer (`apps/viewer` / `bora view`).

## Stack

Vite + React + TypeScript · Tailwind + shadcn/ui · pnpm only  
Visual tokens: inherit [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md).

## Dev

```bash
# Terminal A — Registry (OAuth + org APIs; see services/registry/README.md)
export VITE_REGISTRY_PROXY_TARGET=http://127.0.0.1:8700
uv run --extra registry python -m services.registry.app --host 127.0.0.1 --port 8700

# Terminal B
cd apps/hub
pnpm install
pnpm dev   # http://127.0.0.1:5174  — proxies /v1 → registry
```

| Env | Meaning |
| --- | --- |
| `VITE_REGISTRY_URL` | Absolute Registry origin (production SPA). Empty = same origin (dev proxy). |
| `VITE_REGISTRY_PROXY_TARGET` | Dev proxy target (default `http://127.0.0.1:8080` — use **8700** for local Registry). |

### Login (browser OAuth)

Hub uses **Authorization Code**, not Device Flow. GitHub OAuth App callbacks:

- `http://127.0.0.1:5174/login/callback`
- `http://localhost:5174/login/callback` (if you use that host)

**Sign in with GitHub** → authorize → `/login/callback` → Registry token in
`localStorage` (header shows avatar / display name when available).

CLI stays on Device Flow: `bora login` (see `services/registry/README.md`).

### Invite keys

Org **owners** create keys under Settings. The full key is shown **once** in a
modal; the list only shows a prefix. Members join from **Organizations → Join**.

## Routes

| Path | Page |
| --- | --- |
| `/datasets` | Dataset list (**Your organizations** / **Explore**) |
| `/datasets/:id` | README · Tasks · Leaderboard |
| `/datasets/:id/tasks/:task` | README · Files · Jobs (row opens detail when uploaded) |
| `/organizations` | Your orgs · Join |
| `/organizations/:orgId` | Overview · Settings |
| `/jobs/...` | Remote Attempt detail (tabs + trajectory) |
| `/login` | Starts browser OAuth |
| `/login/callback` | OAuth redirect target |

`:id` is URL-encoded `database_id` (`encodeURIComponent`).

## Related

Epic #22 (catalog) · #38–#40 (files / browse / leaderboard) · #51–#55 (org/share) ·
#43 (optional full Attempt upload for remote Job detail)
