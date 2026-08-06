# BORA local Database viewer

Read-only local UI for a Database package: task list → README / instruction / file tree preview, plus copyable CLI commands.

**Does not** require Registry, Postgres, S3, or OAuth.

## Run

From the repo (or any install that can see `apps/viewer/static`):

```bash
uv run bora view tests/fixtures/databases/suite-min
# opens http://127.0.0.1:8765/
uv run bora view examples/core --port 8770 --no-browser
```

## Layout

| Path | Role |
| --- | --- |
| `static/` | SPA (HTML/CSS/JS, no build step) |
| `src/bora/viewer/` | stdlib HTTP server + safe browse API |

## API (local only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness |
| GET | `/api/database` | Manifest + task ids + suite commands |
| GET | `/api/tasks/{id}` | README / instruction / task.yaml + task commands |
| GET | `/api/tasks/{id}/tree` | File tree under the task directory |
| GET | `/api/tasks/{id}/file?path=` | File preview (text / small image) |

All file access is confined under the opened Database root (path traversal rejected).

## Out of scope (other issues)

- Public Hub catalog / Leaderboard SPA (#22)
- Remote package files API
- Suite metric aggregation (#23)
