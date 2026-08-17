# Author a `bora.plugin/1`

Reference implementations: `plugins/nooa` (real executor), `plugins/dsh`
(DeepSeek Harness JSON-RPC, not ACP), `plugins/slot-probe` (multi-slot probe —
not a business template).

- [Package layout](#package-layout)
- [ExecutorSPI](#executorspi)
- [Trajectory](#trajectory)
- [`image_contribute` + bake](#image_contribute--bake)
- [Hook shape](#hook-shape)
- [Job binding](#job-binding-profiles-not-taskyaml)
- [Typed failures](#typed-failures)
- [Review an existing plugin](#review-an-existing-plugin)
- [Checklist](#checklist)

## Package layout

```text
plugins/my-mech/
├── plugin.yaml                 # format: bora.plugin/1
├── docker/Dockerfile.bake      # only if L1 Ready is required
├── src/my_mech/
│   ├── __init__.py             # must not import BORA Core at package import
│   ├── factory.py              # provide factory (host-only Core imports)
│   ├── hooks.py                # on-handlers
│   └── trajectory.py           # optional: native → bora.trajectory.event/1
└── worker/                     # optional: L1 in-container entry
```

`plugin.yaml` (shipped fields):

```yaml
format: bora.plugin/1
plugin_id: my-mech # = profiles.executor value
version: "0.1.0"
host_requires: # L0 only; omit if the host SPI needs no extra
  - import: my_vendor_sdk
    hint: "uv sync --extra my-mech"
slots:
  provide:
    - id: executor
      priority: 110
      entry: "my_mech.factory:build_executor"
  "on":
    - id: image_contribute
      priority: 110
      entry: "my_mech.hooks:image_contribute"
    - id: trajectory_collect
      priority: 110
      entry: "my_mech.hooks:trajectory_collect"
```

Hub: `package_kind=plugin`. Dataset vs plugin fail-closes; do not mix the two.

`host_requires` allowlist keys: `import`, `file`, `hint`. Unknown keys fail closed.
`import:` is `importlib.util.find_spec` (no spawn). `file:` is relative to the
installed plugin root. Core does not map plugin-id → pip extra. L1 (`provider.kind:
docker`) does **not** consume `host_requires`.

## ExecutorSPI

`src/bora/plugins/protocol.py`:

- `kind: str` (same as `plugin_id` / `profiles.executor`)
- `open(**kwargs)` / `invoke(prompt, *, timeout, workdir, collect_dir, redaction_sentinels)` / `close()`
- optional `bind_to_target(placement: TargetPlacement) -> ExecutorSPI`
- optional `@staticmethod describe() -> dict` (`bora executors -v` / capabilities)

Host factory: `build_executor(**kwargs)`. Common kwargs: `options`, `profile_id`,
`model`, `base_url`, `api_key` (locator name), `plugin_id`.

L1: Core only resolves `TargetPlacement` (`container_id` / uid / gid / workdir /
home). The plugin returns an SPI bound to that target. Missing `bind_to_target`
→ `l1_executor_unbound`. Core must not reconstruct a container executor by kind.

`describe()` keys already in production (copy semantics; do not invent authority):

```text
execution_mode, tools, structured_output, session, stream,
credential_env_names, binary
```

## Trajectory

Layer B: each `AgentResult.events` row has `schema: bora.trajectory.event/1`,
`source` = this plugin id, `session_id` (never `acp_session_id`).
Layer C: only Core `bora.evidence.trajectory.write_trajectory_jsonl` writes
`trajectory.jsonl` (ReAct seq order; do not emit layer-C rows yourself).

`on: trajectory_collect`:

- may map **this** plugin's vendor dump into layer B
- already-contract events whose `source` is not this plugin → **do not** stamp `trajectory_source`
- never emit ACP `session_update`

Vendor native goes to `collect_dir` / `backend_raw/` (e.g. `nooa_events.jsonl`).
If the L1 worker returns JSON on stdout, include mapped `events` and the native
dump; the parent writes `backend_raw`.

When the container does `import my_mech.trajectory`, package `__init__.py` must
not `from my_mech.factory import …` (factory imports `bora`, which is not in
the image).

## `image_contribute` + bake

The handler appends a declare (`{plugin: <id>}`) onto the chain list, then
`return await nxt(base)`. Core `docker buildx`es each **extensions-selected**
installed plugin that registered `image_contribute` and ships
`docker/Dockerfile.bake`. **Context = installed plugin root.**
`executor:` alone does not bake.

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
COPY src/my_mech /opt/my_mech/my_mech
COPY worker/worker.py /usr/local/bin/bora-executor-my-mech
# Pin runtime deps at image build. No invoke-time npm i / floating pip.
RUN chmod 755 /usr/local/bin/bora-executor-my-mech
```

`${BASE_IMAGE}` is usually `bora-attempt:l1` (CPython 3.12). Pin bake-time
wheels to what the worker actually imports; unpinned latest on this base is
not the vendor image. Package `FROM bora-attempt:l1` checkouts: see
`$bora-config-package` `references/isolation.md`.

Do not invent a `docker-package-attempt-<plugin>` image kind. Official ACP
entries do not use this external chain.

## Hook shape

```python
async def trajectory_collect(ctx, value, nxt):
    out = await nxt(value)          # let the rest of the chain run
    # rewrite out or return as-is
    return out
```

`image_contribute` usually mutates `value` (a list) then `await nxt(...)`.

## Job binding (profiles, not task.yaml)

```yaml
format: bora.profiles/1
bindings:
  solver:
    executor: my-mech
    extensions:
      - plugin: my-mech
        options:
          agent: "lib.agents:MyAgent" # plugin-owned, secret-free opaque keys
          method: "run"
    model: openai/glm-5.2
    api_key: ${litellm_api_key} # locator
```

`--set /bindings/<role>/options/<key>=…` writes the **executor plugin**
row (ACP still rejects `command` / engine keys). Other plugins' options
stay on their own `extensions` row. Plugin-owned keys stay opaque to
Core — for example dsh `options.permission` (`read-only` /
`workspace-write` / `danger-full-access`) selects a plugin composition
and child env. Invalid values fail closed at materialize.

## Typed failures

These `kind` / message strings are production fail-closed, not informal logs.

| Signal                                                 | Typical cause                                                              |
| ------------------------------------------------------ | -------------------------------------------------------------------------- |
| `unknown_extension_slot`                               | `plugin.yaml` names a slot not in `slots.py`                               |
| `extension_materialize_failed`                         | factory/options invalid (e.g. ACP missing `options.entry`)                 |
| `l1_executor_unbound`                                  | no `bind_to_target`, or it returned nothing                                |
| `image_contribute_unsatisfied`                         | bound external executor but contribute chain empty or no `Dockerfile.bake` |
| `unsupported executor` / missing from `bora executors` | not installed; Recognition is first-party ∪ `provide(executor)`            |

Host SPI succeeding is **not** L1 Ready. Do not add a silent host fallback.

## Review an existing plugin

```text
session_update | to_acp_shaped | acp_session_id
if kind ==  | make_target_executor | migrated_to_acp
```

Also check: `__init__.py` imports Core? `bind_to_target` present if L1? bake file
if profiles bind this executor on docker tasks? `trajectory_collect` stamps
`trajectory_source` onto foreign `source` rows?

## Checklist

```bash
uv run bora plugin install plugins/my-mech
uv run bora plugin list
uv run bora executors                 # .supported includes my-mech
uv run bora lock <db> --task <id> --profiles path/to/profiles.yaml
uv run bora lock <db> --task <id> --profiles path/to/profiles.yaml --probe
# lock JSON: extension_bindings lists this plugin; no secrets
# --probe: L0 needs declared imports; L1 needs bake file + Docker, not the host extra
```

For L1, run one docker task and confirm bake succeeded and
`execution_location` is not a silent host fallback.
When claiming trajectory: `trajectory.jsonl` has tool/observation rows if the
backend actually used tools; `backend_raw/` stays vendor-native.
