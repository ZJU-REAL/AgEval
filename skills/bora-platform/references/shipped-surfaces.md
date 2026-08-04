# Shipped public surfaces (orientation)

Prefer mechanism packages under `examples/core/` and `examples/l1/`. Full list: `examples/README.md`.

| Package | Demonstrates |
| --- | --- |
| `examples/core/config-minimal` | `bora lock` success |
| `examples/core/attempt-trajectory` | Per-invoke §8.9 trajectory + `Result.logs` |
| `examples/core/builtin-executor-conformance` | Profile-only codex/pi/opencode switch |
| `examples/core/builtin-executor-mixed` | Two executors, independent trees |
| `examples/core/hard-ceiling-trajectory` | N+1 invoke denied pre-effect |
| `examples/core/environment-action-denied` | Env action deny-before-mutation |
| `examples/core/orchestration-environment` | Multi-profile + Postgres + effects |
| `examples/l1/builtin-executor-visibility` | L1 assurance + execution_location |
| `examples/l1/builtin-executor-visibility-denied` | Gold not visible |

## Install (repo root)

```bash
uv sync --frozen --all-packages
uv run bora --help
```

Design anchors: `docs/design/00-overview-and-product.md`, `docs/design/01-bora-core.md`, `docs/design/09-owner-matrix-and-structure.md`.
