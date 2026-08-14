# Shipped public surfaces (orientation)

Prefer mechanism packages under `examples/core/` and `examples/l1/`. Full list: `examples/README.md`.

| Package | Demonstrates |
| --- | --- |
| `examples/core --task config-minimal` | `bora lock` success |
| `examples/core --task sdk-agent-session` | Host multi-invoke + independent PASS |
| `examples/core --task attempt-trajectory` | Per-invoke Core `trajectory.jsonl` + `Result.logs` |
| `examples/core --task builtin-executor-conformance` | Profile-only switch (`executor: Official/acp` + `options.entry`) |
| `examples/core --task builtin-executor-mixed` | Two ACP profiles, independent sessions/trees |
| `examples/core --task hard-ceiling-trajectory` | N+1 invoke denied pre-effect |
| `examples/core --task environment-action-denied` | Env action deny-before-mutation |
| `examples/core --task plugin-agent-executor` | Second executor mechanism (`openai-http`) |
| `examples/l1 --task sdk-session-single-actor` | L1 SDK session → attempt-container |
| `tests/provider_l1/test_harness_isolation_contracts.py` | Gold hide / no-cred harness / writer-stop (Provider) |
| `examples/journeys/*` | Case-class demos (env / multiagent / tau2 / terminal) |

## Install (repo root)

```bash
uv sync --frozen --all-packages
uv run bora --help
uv run bora executors -v   # executor kinds + ACP entry readiness
```

Design anchors: `docs/design/00-overview-and-product.md`, `docs/design/01-bora-core.md`, `docs/design/05-runtime/agent-service.md` / `evidence.md`, `docs/design/09-owner-matrix-and-structure.md`.
