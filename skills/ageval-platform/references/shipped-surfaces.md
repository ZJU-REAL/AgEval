# Shipped public surfaces (orientation)

Prefer mechanism packages under `examples/core/`. Full list: `examples/README.md`.
Evidence grade is **limited `runnable-mvp`**. Do not claim `isolated` from one happy path.

| Package | Demonstrates |
| --- | --- |
| `examples/core --task config-minimal` | `ageval lock` success (`dataset_id`, no `database_id`) |
| `examples/core --task acp-local-min` | local ACP public run |
| `examples/core --task acp-docker-min` | docker ACP public run (`--profiles examples/core/profiles.docker.yaml`) |
| `examples/core --task sdk-agent-session` | Host multi-invoke + independent PASS |
| `examples/core --task plugin-agent-executor` | Second executor mechanism (`openai-http`) |
| `examples/journeys --task terminal-jsonl-agg` | Named journey |
| `examples/journeys --task env-postgres-min` | Sidecar / compose path |
| docker topology `sdk-session-single-actor` | lock 有 topology 即可 |

e2b / ssh / daytona: code exists; missing key → `--probe` `ready: false`. Skip ≠ pass.

## Install (repo root)

```bash
uv sync --frozen --all-packages
uv run ageval --help
uv run ageval executors -v
```

Design: `docs/design/00-overview-and-product.md`, `docs/design/01-ageval-core.md`, `ARCHITECTURE.md`.
