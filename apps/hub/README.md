# BORA Hub (`apps/hub`)

Registry **Dataset catalog** SPA (Epic #22): list public/private packages, open
README + tasks, preview package files, Task Jobs list, Leaderboard (#40).

Also: **Organizations** browse (membership, org datasets, shared suite results)
and **GitHub browser login** (Authorization Code → Registry token).

**Not** the local results viewer (`apps/viewer` / `bora view`).

## Stack

Vite + React + TypeScript · Tailwind + shadcn/ui · pnpm only  
Visual tokens: inherit [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md).

## Dev

```bash
# Terminal A — Registry (must expose OAuth + org APIs)
# see services/registry/README.md
export VITE_REGISTRY_PROXY_TARGET=http://127.0.0.1:8700   # recommended local port
uv run --extra registry python -m services.registry.app --host 127.0.0.1 --port 8700

# Terminal B
cd apps/hub
pnpm install
pnpm dev   # http://127.0.0.1:5174  — proxies /v1 → registry
```

| Env | Meaning |
| --- | --- |
| `VITE_REGISTRY_URL` | Absolute Registry origin (production SPA). Empty = same origin (dev proxy). |
| `VITE_REGISTRY_PROXY_TARGET` | Dev proxy target (default `http://127.0.0.1:8080` — set to **8700** for local Registry). |

### Login (browser OAuth)

Hub uses **Authorization Code** (not Device Flow). Configure the GitHub OAuth App
callback URL:

- `http://127.0.0.1:5174/login/callback`
- `http://localhost:5174/login/callback` (if you open Hub that way)

Flow: **Sign in with GitHub** → GitHub Authorize → `/login/callback` → Registry
token in `localStorage` (avatar + display name in the header when returned).

CLI remains Device Flow: `bora login` (see `services/registry/README.md`).

## Routes

| Path | Page |
| --- | --- |
| `/datasets` | Dataset list (**Your organizations** / **Explore**) |
| `/datasets/:id` | README · Tasks · Leaderboard |
| `/datasets/:id/tasks/:task` | README · Files · Jobs (list only) |
| `/organizations` | Orgs you belong to |
| `/organizations/:orgId` | Members · Datasets · Shared results · Settings placeholder |
| `/login` | Start browser OAuth |
| `/login/callback` | OAuth redirect target |

`:id` is URL-encoded `database_id` (`encodeURIComponent`).

## Related issues

- Epic #22 · files API #38 · browse #39 · Leaderboard #40 · org/share #51–#55 · Jobs deep-link #43 (out of scope)
