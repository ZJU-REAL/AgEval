# BORA Viewer

Local Harbor-style results console for a Database package:

**Jobs → Tasks → Trial**, with search, sortable columns, breadcrumbs, and copyable CLI.

## Design

- [DESIGN.md](./DESIGN.md) — Vercel-inspired tokens + IA
- [AGENTS.md](./AGENTS.md) — implementation constraints (shadcn, no hand-rolled chrome)

## Develop

```bash
# Terminal A: API + static (after build) or API only
uv run bora view tests/fixtures/databases/suite-min --port 8765 --no-browser

# Terminal B: Vite HMR (proxies /api → :8765)
cd apps/viewer
npm install
npm run dev
```

## Production build (required for `bora view`)

```bash
cd apps/viewer
npm install
npm run build   # writes dist/
uv run bora view <database>
```

Python serves `apps/viewer/dist/` preferentially over the legacy `static/` shell.

## API

| Path | Description |
| --- | --- |
| `GET /api/jobs` | Suite runs under `.bora/suite-runs/` |
| `GET /api/jobs/{id}` | Job + task rows |
| `GET /api/jobs/{id}/tasks/{task_id}` | Trial detail + `bora run` command |
