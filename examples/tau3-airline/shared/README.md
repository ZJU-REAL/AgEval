# Dataset `shared/` (tau3-airline)

| Path | Role |
| --- | --- |
| `lib/` | Harness + evaluator bridge modules (import only; not Agent-mounted) |
| `assets/` | Domain fixtures (`db.json`, `policy.md`, `tasks.json`, …) via code paths |

Top-level import names under `lib/` must **not** collide with any `tasks/*/lib/`.
Changing anything here changes whole-package `packageDigest`.
