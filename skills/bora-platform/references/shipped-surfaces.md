# Shipped public surfaces (orientation)

Prefer mechanism packages under `examples/core/` and `examples/l1/`. Full list: `examples/README.md`.

| Package | Demonstrates |
| --- | --- |
| `examples/core/config-minimal` | `bora lock` success |
| `examples/core/sdk-agent-session` | Host multi-invoke + independent PASS |
| `examples/core/attempt-trajectory` | Per-invoke §8.9 trajectory + `Result.logs` |
| `examples/core/builtin-executor-conformance` | Profile-only switch (`executor: acp` + `options.entry`) |
| `examples/core/builtin-executor-mixed` | Two ACP profiles, independent sessions/trees |
| `examples/core/hard-ceiling-trajectory` | N+1 invoke denied pre-effect |
| `examples/core/environment-action-denied` | Env action deny-before-mutation |
| `examples/core/plugin-agent-executor` | Second executor mechanism (`openai-http`) |
| `examples/l1/sdk-session-single-actor` | L1 SDK session → attempt-container |
| `tests/provider_l1/test_harness_isolation_contracts.py` | Gold hide / no-cred harness / writer-stop (Provider) |
| `examples/journeys/*` | Case-class demos (env / multiagent / tau2 / terminal) |

## Install (repo root)

```bash
uv sync --frozen --all-packages
uv run bora --help
uv run bora executors -v   # executor kinds + ACP entry readiness
```

Design anchors: `docs/design/00-overview-and-product.md`, `docs/design/01-bora-core.md`, `docs/design/05-runtime-core.md` §8.4.3a / §8.9, `docs/design/09-owner-matrix-and-structure.md`.
