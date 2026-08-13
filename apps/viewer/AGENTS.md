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
   Jobs = suite runs under `.bora/suite-runs/` and single-task Attempts under `.bora/runs/`
2. **Job → tasks** — task table with scores / status / agent-model meta
3. **Task detail** — trials/run row(s), status/error coloring, **copyable CLI**
4. **Attempt / trial detail** — `Jobs > job > task > run_id`; Outcome + actors
   (Role / Agent / Model / Time / Usage) + tabs from real evidence only
   (Trajectory · Agent · Verifier · Artifacts · Lock · Runtime). Top bar may show
   framework / docker / `provenance.upstream.url`. Multi-role groups Trajectory
   and Agent tree by `profile_id`. Usage/trajectory are observational ≠ PASS.
5. **Breadcrumb** — `Jobs > jobId > taskId > runId` with `>` separators; click to navigate

**Out of scope unless user asks:**

- Public catalog, OAuth, Postgres, Leaderboard SPA (#22)
- Package file-tree / task-package browser (removed; Jobs is the product surface)
- Marketing mesh gradients, dark neon skins, custom CSS component kits
- Fabricating Harbor-only files or empty evidence tabs

## Stack (mandatory)

| Layer | Choice |
| --- | --- |
| Build | Vite + React + TypeScript |
| Package manager | **pnpm** only (`packageManager` field; not npm/yarn) |
| Styling | Tailwind CSS v4 (or v3 if tooling forces) |
| Components | **shadcn/ui** (Radix primitives) — own the source under `src/components/ui/` |
| Icons | lucide-react (shadcn default) — one family only |
| Table | shadcn Table patterns (sortable heads in-app) |
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
| `GET /api/jobs` | Job list (suite-runs + single-task Attempts) |
| `GET /api/jobs/{id}` | Job detail + task rows |
| `GET /api/jobs/{id}/tasks/{task_id}` | Task detail + enriched trials list + commands |
| `GET /api/jobs/{id}/tasks/{task_id}/trials` | Trials list (suite + local evidence) |
| `GET /api/jobs/{id}/tasks/{task_id}/trials/{run_id}` | Attempt meta + `available_tabs` |
| `GET .../trials/{run_id}/tree?scope=` | File tree under evidence (`agent`/`verifier`/`runtime`/…) |
| `GET .../trials/{run_id}/file?path=` | File preview (size-capped; secret-like names redacted) |
| `GET .../trials/{run_id}/trajectory` | Parsed `trajectory.jsonl` steps (observational) |

Trial meta returns `framework` / `docker` / `upstream_url` (and related provenance
fields) plus `actors[]` from lock + invocation metadata: role · agent · model ·
Time (`time_label` / `latency_ms_sum`) · Usage (`usage_label` / normalized last-inv
usage). Cache hit rate uses inclusion/disjoint heuristics; never treat
`UsageUpdate.used` as billable tokens.

| Tab | Disk scope | Meaning |
| --- | --- | --- |
| **Artifacts** | `artifacts/`, `harness/`, `agent/artifacts/` | Harness-published product files (JSON results, terminal, etc.) |
| **Runtime** | root `effects.jsonl`, `cleanup.json`, `summary.json`, `agent.json`, `harness.json` | Attempt bookkeeping — not publishable outputs |
| **Agent** | `agent/` | Invocation trees, trajectory raw, backend_raw |
| **Verifier** | `evaluation/`, `eval_staging/`, `result.json` | Evaluator side |

SPA file preview: JSON/JSONL pretty-print + lightweight syntax highlight (no extra deps).

Package-file browse routes (`/api/database`, `/api/tasks/*`, `/api/commands`) were removed with the old SPA.  
All paths confined to the opened Database root (`job_id` / `task_id` / `run_id` single-segment; file paths fail closed on `..`). No Registry required.  
Evidence roots: `{db}/.bora/runs/{run_id}` or task-local `.bora/runs/`; lock `task_id` must match when present.

## Build & serve

```bash
# from apps/viewer — pnpm only (not npm)
pnpm install
pnpm build          # → dist/
# from repo root
uv run bora view <database> --no-browser
```

Python must serve **`apps/viewer/dist/`** (production build). There is **no** separate `static/` source tree.  
Dev: `bora view --dev` starts the API and tries to spawn Vite. If that cannot run, it prints `pnpm --dir apps/viewer dev`. Same API as production `bora view`. Deep-link with `--open /jobs/...`.

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
