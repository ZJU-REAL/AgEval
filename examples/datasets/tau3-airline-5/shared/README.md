# Dataset `shared/` (tau3-airline-5)

| Path | Role |
| --- | --- |
| `lib/` | Harness + evaluator bridge modules — import as `shared.lib.*` (not Agent-mounted) |
| `assets/` | Domain fixtures (`db.json`, `policy.md`, `tasks.json`, …) via code paths |

Task members must **not** own a top-level name `shared` (dir or `shared.py`).
Same basename under `shared/lib` and a task `lib/` is fine under namespaced imports.
Changing anything here changes whole-package `packageDigest`.
