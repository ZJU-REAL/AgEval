# BORA Viewer — Agent constraints

This directory is the **local Database / suite-results Web UI**.
Python serves the built SPA; React app lives here.

## Authority

| Doc | Role |
| --- | --- |
| [DESIGN.md](./DESIGN.md) | Visual + IA authority (Vercel-inspired product chrome) |
| This file | Implementation constraints for agents |
| `src/bora/viewer/` | HTTP API + static file serving (stdlib) |

When UI conflicts with taste: **DESIGN.md wins**.

## Product surface (scope lock)

**In scope (MVP):**

1. **Jobs list** — search; filter dropdowns; sortable columns; row click  
   Jobs = local suite runs under `.bora/suite-runs/`
2. **Job → tasks** — task table with scores / status / agent-model meta
3. **Task detail** — trials/run row(s), status/error coloring, **copyable CLI**
4. **Breadcrumb** — `Jobs > jobId > taskId` with `>` separators; click to navigate

**Out of scope unless user asks:**

- Public catalog, OAuth, Postgres, Leaderboard SPA (#22)
- Package file-tree browser as primary UX
- Marketing mesh gradients, dark neon skins, custom CSS component kits

## Stack (mandatory)

| Layer | Choice |
| --- | --- |
| Build | Vite + React + TypeScript |
| Package manager | **pnpm** only (`packageManager` field; not npm/yarn) |
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
2. Keep **product chrome**: near-white (light) or near-black (dark) canvas, ink text, hairline borders.
3. **Tabular nums** for scores, rates, durations, trial fractions.
4. Mono **only** for commands, digests, technical IDs.
5. No em-dash (`—`) in UI strings.
6. Primary CTA color is ink; link blue for true hyperlinks only (CLI strips use shell highlight).
7. Error / exception text uses the design-token error color.
8. Prefer density of a results console, not an art gallery landing page.

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
# from apps/viewer — pnpm only (not npm)
pnpm install
pnpm build          # → dist/
# from repo root
uv run bora view <database> --no-browser
```

Python must serve **`apps/viewer/dist/`** (production build). There is **no** separate `static/` source tree.  
Dev: `pnpm dev` proxies `/api` to the Python viewer port when both run.

## Theme

- Modes: **light** | **dark** | **system** (default system).
- Toggle in top-right header; persist `localStorage` key `bora-viewer-theme`.
- Tokens via `data-theme` + CSS variables in `src/index.css`.

## CLI command strip

- Render with shell-style highlighting (not flat link-blue).
- Dark code surface (`code-bg`); token kinds: cmd / flag / string / path / plain.

## Delivery rules

- Prefer phase commits: design docs → API → scaffold → pages → polish.
- Do not claim #22 Leaderboard done.
- Keep tests green: `uv run pytest tests/viewer/ -q` and `pnpm build`.
- Column labels map BORA fields for operators, e.g. `Result` ≈ `mean_score` / `pass_rate`, `Trials` ≈ task counts.

## Anti-patterns (reject in review)

- Recreating ad-hoc full-page CSS SPA as default
- Fake marketing hero inside the results console
- Ignoring breadcrumb click-through
- Unsortable tables when columns are metric-like
- Shipping unbuilt `src/` only (always produce `dist/` for `bora view`)
