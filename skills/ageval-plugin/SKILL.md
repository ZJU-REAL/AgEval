---
name: ageval-plugin
description: >
  Author and review ageval mechanism plugins (ageval.plugin/1): extension slots L0–L5,
  registry resolve, ExecutorSPI + bind_to_target, image_contribute bake, neutral
  trajectory events, Recognition ≠ L0 host-ready ≠ L1 bake-declared. Use when writing or reviewing plugins/,
  plugin.yaml, provide(executor), on-handlers, Dockerfile.bake, or asking "how do
  plugins work", "write a plugin", "add an executor", "extension_bindings",
  "image_contribute", "bind_to_target", "l1_executor_unbound". Not an app store.
  Never invent slots or dual-path Core factories.
---

# ageval plugins

Plugins extend **how** work runs (executor / env / trajectory / bake). They do
not own the package harness loop. Not an app store. Not a Core patch.

Authority: `docs/design/11-extension-plugins.md`. Map: `ARCHITECTURE.md`.
Slot ids: `src/ageval/plugins/slots.py`.

## Mechanism (read this first)

The host declares **fixed slots**. A plugin contributes only to those slots.
Registry has `on` and `provide`. Resolve: explicit binding wins; else compare
priority; a tie **fail-closes**.

```text
profiles.executor / extensions  →  registry resolve
  provide(executor)  single winner  →  factory(**kwargs) → ExecutorSPI
  on(slot)           ordered chain  →  await handler(ctx, value, nxt)
lock writes extension_bindings (into the digest)
```

| Kind | Meaning | Examples |
| --- | --- | --- |
| **provide** | Single winner | `executor`, `env_action`, `trajectory_seal`, `evaluation_runtime` |
| **multi (`on`)** | `(ctx, value, nxt)` chain; may rewrite or short-circuit | `image_contribute`, `trajectory_collect`, phase bookends |

Handlers are **awaited** at the control point with a live `ctx`. Do not dump
`{kind: shell, argv:…}` rows for Core to interpret later.

### Ownership

| Core keeps | Plugin does | Forbidden |
| --- | --- | --- |
| lock / Attempt / isolation / hard ceilings / evaluator PASS | Mechanism: call the backend, bake, map events | Invent PASS; branch by bench/task name |
| Layer-C `trajectory.jsonl` writer | Layer B: vendor native → `ageval.trajectory.event/1` | ACP `session_update` masquerade |
| `TargetPlacement` (container / uid / workdir) | `bind_to_target(placement)` | Core `if kind == …` reconstructing executors |
| Credential **projection** (locator → scoped env) | Use only projected env | Secrets in lock / plugin.yaml / evidence |

`ageval plugin install` writes **only** `$AGEVAL_HOME/plugins` (default `~/.ageval/plugins`).
It **never** rewrites `profiles.yaml` / `task.yaml` / harness. A declared
`plugin_requires` row is installed first: short `name` is cache or local
sibling only (never Hub); `org/name` fetches that exact Hub package.

### Recognition ≠ L0 host-ready ≠ L1 bake-declared

| Stage | Meaning |
| --- | --- |
| install / `ageval plugin list` / lock recognizes the kind | **Recognition** |
| declared `host_requires` satisfied (L0) | **L0 host-ready** |
| profiles bind `executor: <plugin_id>` | Job selection |
| `image_contribute` + `docker/Dockerfile.bake` chained buildx | **L1 bake-declared** |

Bound external executor with an empty contribute chain or missing bake file →
L1 **fail-closed**. Install success ≠ runnable in the container. Official ACP
entries stay bake-in on `docker/attempt`; they do not use this external bake.

### Switch mechanism in config, not in harness

Same harness: edit Database `profiles.yaml` (or `--profiles` /
`--set /bindings/<role>/…`). Member `task.yaml` declares role slots only —
no inline executor / options.

## Authoring order

1. Pick slots against `slots.py` + [references/mechanism.md](references/mechanism.md). Do not invent ids.
2. New `ageval.plugin/1` package (`plugin.yaml` + code). Name by **protocol / resource / execution mechanism**, never by benchmark.
3. `provide(executor)` implements `ExecutorSPI`; L1 must `bind_to_target`. See [references/authoring.md](references/authoring.md).
4. For L1: `on: image_contribute` + `docker/Dockerfile.bake` (context = plugin root). Core does **not** interpret bake tokens by plugin name.
5. Events: `AgentResult.events` must be `ageval.trajectory.event/1`. `trajectory_collect` only maps **this** plugin's native dump; do not stamp another producer's `source`.
6. In-container worker: package `__init__.py` must **not** import ageval Core (or `import plugin.trajectory` dies in the image).
7. `ageval plugin install <path>` → `ageval lock` (`extension_bindings`) → `ageval executors` (Recognition) → then L1 bake.

## Red lines

1. Trajectory ≠ PASS. Extension chains do not choose PASS.
2. No `ageval.agent_executors` / `resolve_executor` dual path. Selection is registry provide only.
3. Non-ACP plugins must not emit ACP `session_update` shapes.
4. `api_key` in profiles is an **env locator name**; the value never enters lock.
5. Do not clone first-party contrib (`acp` / `openai-http`) as an external package. External packages live under `plugins/` and stay out of Core bootstrap.

## CLI (shipped)

```bash
uv run ageval plugin install plugins/nooa
uv run ageval plugin list
uv run ageval plugin uninstall nooa
uv run ageval executors          # Recognition + L0 host_ready + l1_bake_declared
uv run ageval lock <db> --task <id> --profiles path/to/profiles.yaml
uv run ageval lock <db> --task <id> --profiles path/to/profiles.yaml --probe
uv run ageval run  <db> --task <id> --profiles path/to/profiles.yaml
```

Discover flags with `ageval plugin --help`. Do not invent commands.

## References (after the mechanism)

| Path | Use |
| --- | --- |
| [references/mechanism.md](references/mechanism.md) | Slot layers, resolve, lock, ACP coexistence |
| [references/authoring.md](references/authoring.md) | Package layout, SPI, bake, trajectory, typed failures, review grep |
| `docs/design/11-extension-plugins.md` | Design authority |
| `docs/design/05-runtime/evidence.md` | Three-layer trajectory contract |
| `src/ageval/plugins/slots.py` / `protocol.py` | Slot ids and `ExecutorSPI` |
| `plugins/nooa` | External executor + bake + neutral trajectory |
| `plugins/dsh` | External DeepSeek Harness JSON-RPC executor + bake (not ACP); `options.permission` is plugin-owned |
| `plugins/slot-probe` + `examples/slot-probe` | Multi-slot on-handler regression, not a business template |

Siblings: orientation → `$ageval-platform`; CLI → `$ageval-cli`; Database/profiles → `$ageval-config-package`; harness → `$ageval-sdk-harness`.
