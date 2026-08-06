# BORA Viewer — Agent constraints

This directory is the **local Database / suite-results Web UI**.
Python serves the built SPA; React app lives here.

## Authority

| Doc | Role |
| --- | --- |
| [DESIGN.md](./DESIGN.md) | Visual + IA authority (Vercel-inspired, Harbor drill-down) |
| This file | Implementation constraints for agents |
| `src/bora/viewer/` | HTTP API + static file serving (stdlib) |
| Issue #21 / Harbor `http://127.0.0.1:8080/` | Functional reference for Jobs → Tasks → Trial |

When UI conflicts with taste: **DESIGN.md wins**.

## Product surface (scope lock)

**In scope (Harbor-equivalent MVP):**

1. **Jobs list** — search; filter dropdowns; sortable columns; row click
2. **Job → tasks** — task table with scores / status / agent-model meta
3. **Task detail** — trials/run row(s), status/error coloring, **copyable CLI**
4. **Breadcrumb** — `Jobs > jobId > taskId` with `>` separators; click to navigate

**Out of scope unless user asks:**

- Public Hub catalog, OAuth, Postgres, Leaderboard SPA (#22)
- Package file-tree browser as primary UX (old hand-rolled UI)
- Marketing mesh gradients, dark neon skins, custom CSS component kits

## Stack (mandatory)

| Layer | Choice |
| --- | --- |
| Build | Vite + React + TypeScript |
| Styling | Tailwind CSS v4 (or v3 if tooling forces) |
| Components | **shadcn/ui** (Radix primitives) — own the source under `src/components/ui/` |
| Icons | lucide-react (shadcn default) — one family only |
| Table | TanStack Table **or** shadcn Table patterns |
| Routing | react-router-dom (client routes under SPA) |
| Fonts | Geist if vendored; else Inter + system mono |

**Forbidden:**

- Hand-rolled full CSS design system replacing shadcn
- Second component library (MUI, Ant, Chakra, Bootstrap)
- Inline style soup for layout chrome
- Google Fonts CDN in production (prefer self-host / system stack)

## Design discipline

1. Read [DESIGN.md](./DESIGN.md) before changing colors, type, or density.
2. Keep **light product chrome**: white/near-white canvas, ink text, hairline borders.
3. **Tabular nums** for scores, rates, durations, trial fractions.
4. Mono **only** for commands, digests, technical IDs.
5. No em-dash (`—`) in UI strings.
6. Primary CTA color is ink `#171717`; link blue `#0070f3` for command links only.
7. Error / exception text uses `#ee0000` (Harbor-like).
8. Prefer density of a data console (Harbor), not an art gallery landing page.

## Backend contract

Python API under `/api/*` (see `src/bora/viewer/`):

| Path | Purpose |
| --- | --- |
| `GET /api/health` | Liveness |
| `GET /api/database` | Database meta + commands |
| `GET /api/jobs` | Suite-run job list (local `.bora/suite-runs`) |
| `GET /api/jobs/{id}` | Job detail + task rows |
| `GET /api/jobs/{id}/tasks/{task_id}` | Task / trial detail + commands |

All paths confined to the opened Database root. No Registry required.

## Build & serve

```bash
# from apps/viewer
npm install
npm run build          # → dist/
# from repo root
uv run bora view <database> --no-browser
```

Python must serve **`dist/`** (production build). Dev: `npm run dev` proxies `/api` to the Python viewer port when both run.

## Delivery rules

- Prefer phase commits: design docs → API → scaffold → pages → polish.
- Do not claim #22 Leaderboard done.
- Keep tests green: `uv run pytest tests/viewer/ -q` and `npm run build`.
- When adding columns, match Harbor naming where BORA has data (`Result` ≈ `mean_score` / `pass_rate`; `Trials` ≈ task counts).

## Anti-patterns (reject in review)

- Recreating the old dark sidebar + custom CSS SPA as default
- Fake marketing hero inside the results console
- Ignoring breadcrumb click-through
- Unsortable tables when columns are metric-like
- Shipping unbuilt `src/` only (always produce `dist/` for `bora view`)
