# BORA Viewer

Local results console for a Database package:

**Jobs → Tasks → Trial**, with search, sortable columns, breadcrumbs, and copyable CLI.

## Design

- [DESIGN.md](./DESIGN.md) — Vercel-inspired tokens + IA
- [AGENTS.md](./AGENTS.md) — implementation constraints (shadcn, no hand-rolled chrome)

## Develop

```bash
# Terminal A: API (after pnpm build) 
uv run bora view tests/fixtures/databases/suite-min --port 8765 --no-browser

# Terminal B: Vite HMR (proxies /api → :8765)
cd apps/viewer
pnpm install
pnpm dev
```

## Production build (required for `bora view`)

```bash
cd apps/viewer
pnpm install
pnpm build   # writes dist/
uv run bora view <database>
```

Package manager: **pnpm** only (`packageManager` field; do not use npm/yarn).

Python serves **`apps/viewer/dist/`** only (no separate `static/` tree).

## API

| Path | Description |
| --- | --- |
| `GET /api/jobs` | Suite runs under `.bora/suite-runs/` |
| `GET /api/jobs/{id}` | Job + task rows |
| `GET /api/jobs/{id}/tasks/{task_id}` | Trial detail + `bora run` command |
