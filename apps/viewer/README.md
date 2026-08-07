# BORA Viewer

Local results console for a Database package:

**Jobs → Tasks → Attempt (trial / run_id)**, with search, sortable columns, breadcrumbs, and copyable CLI.

## What you see

| Layer | Content |
| --- | --- |
| **Jobs** | Local suite runs under `.bora/suite-runs/` |
| **Tasks** | Per-task status / score / run refs from suite summary (+ local evidence when present) |
| **Attempt** | One `run_id`: outcome strip, actors table, evidence tabs |

### Attempt detail (highlights)

- **Subtitle**: `task · framework · docker · upstream.url` (omit missing; url is an external link when present)
- **Actors**: Role / Agent / Model / **Time** / **Usage**
  - Time = sum of inv `latency_ms` for that `profile_id`
  - Usage = last inv normalized ACP usage for that profile (tokens / cache hit / cost when reported)
  - Fail-open `-` when the entry did not report usage (e.g. some `pi` / `grok-build` paths)
  - Observational only — trajectory and usage are **not** PASS authority
- **Tabs** (only if files exist): Trajectory · Agent · Verifier · Artifacts · Lock · Runtime
- **Multi-role**: Trajectory steps and Agent tree group by `profile_id` (virtual folders; on-disk layout unchanged)

SPA lives under `src/`; Python serves the built `dist/` only.

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

If the port is already in use, stop the other `bora view` process or pass `--port <free>` (`--port 0` = ephemeral). The CLI error includes a concrete `http://host:port/` URL.

## Production build (required for `bora view`)

```bash
cd apps/viewer
pnpm install
pnpm build   # writes dist/
uv run bora view <database>
```

Package manager: **pnpm** only (`packageManager` field; do not use npm/yarn).

Python serves **`apps/viewer/dist/`** only (no separate `static/` tree). `dist/` is gitignored.

## API

| Path | Description |
| --- | --- |
| `GET /api/health` | Liveness |
| `GET /api/jobs` | Suite runs under `.bora/suite-runs/` |
| `GET /api/jobs/{id}` | Job + task rows |
| `GET /api/jobs/{id}/tasks/{task_id}` | Task detail, trials list, copyable `bora run` |
| `GET /api/jobs/{id}/tasks/{task_id}/trials` | Trials (suite + local evidence) |
| `GET .../trials/{run_id}` | Attempt meta: status, actors (Time/Usage), framework, docker, provenance, `available_tabs` |
| `GET .../trials/{run_id}/tree?scope=` | Evidence file tree (`agent` / `verifier` / `artifacts` / `lock` / `runtime` / …) |
| `GET .../trials/{run_id}/file?path=` | File preview (size-capped; secret-like names redacted) |
| `GET .../trials/{run_id}/trajectory` | Parsed `trajectory.jsonl` steps (observational; steps carry `profile_id` when known) |

All ids are single path segments; file paths fail closed on `..`. No Registry required for local browse.
