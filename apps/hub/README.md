# BORA Hub (`apps/hub`)

Registry **Dataset catalog** SPA (Epic #22): list public/private packages, open
README + tasks, preview package files, Task Jobs list, Leaderboard (#40).

**Not** the local results viewer (`apps/viewer` / `bora view`).

## Stack

Vite + React + TypeScript · Tailwind + shadcn/ui · pnpm only  
Visual tokens: inherit [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md).

## Dev

```bash
# Terminal A — Registry (example)
# see services/registry/README.md

# Terminal B
cd apps/hub
pnpm install
pnpm dev   # http://127.0.0.1:5174  — proxies /v1 → registry
```

| Env | Meaning |
| --- | --- |
| `VITE_REGISTRY_URL` | Absolute Registry origin (production SPA). Empty = same origin (dev proxy). |
| `VITE_REGISTRY_PROXY_TARGET` | Dev proxy target (default `http://127.0.0.1:8080`). |

## Routes

| Path | Page |
| --- | --- |
| `/datasets` | Dataset list |
| `/datasets/:id` | README · Tasks · Leaderboard |
| `/datasets/:id/tasks/:task` | README · Files · Jobs (list only) |
| `/login` | GitHub device login shell |

`:id` is URL-encoded `org/name` (`encodeURIComponent`).

## Related issues

- Epic #22 · files API #38 · browse #39 · Leaderboard #40 · Jobs click-through #43 (out of scope)
