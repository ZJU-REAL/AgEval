# Author a `ageval.plugin/1`

Reference implementations: `plugins/nooa` (executor), `plugins/dsh`
(DeepSeek JSON-RPC, not ACP), `plugins/home-files` (chain). Design:
`docs/design/11-extension-plugins.md`.

Slots are **exclusive** and **chain** only. Do not invent extra slot kinds.

## Package layout

```text
plugins/my-mech/
├── plugin.yaml                 # format: ageval.plugin/1
├── docker/Dockerfile.bake      # optional: docker image layers
├── src/my_mech/
│   ├── __init__.py             # must not import ageval Core at package import
│   ├── factory.py
│   ├── hooks.py
│   └── trajectory.py           # optional: native → ageval.trajectory.event/1
└── worker/                     # optional: in-box entry
```

```yaml
format: ageval.plugin/1
plugin_id: my-mech
version: "0.1.0"
description: "One paragraph Hub shows above Install (CLI). Links: [text](https://example.com)."
host_requires:
  - import: my_vendor_sdk
    hint: "uv sync --extra my-mech"
slots:
  exclusive:
    - id: executor
      priority: 110
      entry: "my_mech.factory:build_executor"
  chain:
    - id: trajectory_collect
      priority: 110
      entry: "my_mech.hooks:trajectory_collect"
inject:
  - service: environment
    capabilities: [exec, upload]   # ACP uses attach_stdio instead
config:
  image_layers: docker/Dockerfile.bake
```

Hub: `package_kind=plugin`. Dataset vs plugin fail-closes.
`description` is optional Hub copy (one paragraph above Install (CLI)). Empty / non-string fails closed. Markdown links (`[text](https://…)`) render on Hub; other block syntax does not.

`host_requires` allowlist keys: `import`, `file`, `hint`. Unknown keys fail closed.
`import:` is `importlib.util.find_spec` (no spawn). Core does not map plugin-id → pip extra.
docker kind does **not** consume `host_requires` (image bake does).

An environment plugin fills exclusive slot `environment` and implements
`src/ageval/environments/protocol.py`. Do not import docker/e2b/ssh from ACP.

## Executor

Host factory: `build_executor(**kwargs)`. Common kwargs: `options`, `profile_id`,
`model`, `base_url`, `api_key` (locator name), `host`, `placement`, `package_root`.

ACP attaches with `host.attach_stdio`. dsh / nooa run a baked (or uploaded)
worker with `host.exec` and `host.upload`. Missing capability → lock fails.
Core must not reconstruct a container executor by kind. No silent host fallback.

`describe()` keys already in production (copy semantics):

```text
execution_mode, tools, structured_output, session, stream,
credential_env_names, binary
```

## Trajectory

Layer B: each event row has `schema: ageval.trajectory.event/1`, `source` = this plugin id, `session_id`.
Layer C: only Core writes `trajectory.jsonl`. Plugins must not emit layer-C rows.

`trajectory_collect` may map **this** plugin's vendor dump into layer B.
Never stamp `trajectory_source` onto another plugin's `source`. Never emit ACP `session_update`.

When the container does `import my_mech.trajectory`, package `__init__.py` must
not import the Core-touching factory.

## Image layers (docker bake)

Not a timeline slot. The environment winner reads `config.image_layers` at `host.start()`.
`executor:` alone does not bake. Context = installed plugin root. Pin wheels at
image build. No invoke-time `npm i` / floating pip. Official ACP entries do not
use this external chain.

`${BASE_IMAGE}` is usually `ageval-attempt:base` (CPython 3.12).

## Hook shape

```python
async def trajectory_collect(ctx, value, nxt):
    out = await nxt(value)
    return out
```

## Job binding (profiles, not task.yaml)

```yaml
format: ageval.profiles/1
environment: docker
agent_profiles:
  solver:
    executor: my-mech
    extensions:
      - plugin: my-mech
        options:
          agent: "lib.agents:MyAgent"
          method: "run"
    model: openai/glm-5.2
    api_key: ${litellm_api_key}
```

`--set /bindings/<role>/options/<key>=…` writes the executor plugin row
(ACP still rejects `command` / engine keys). YAML key is `agent_profiles`.

## Typed failures

| Signal | Typical cause |
| --- | --- |
| `unknown_extension_slot` | `plugin.yaml` names a slot not in `slots.py` |
| `extension_materialize_failed` | factory/options invalid (e.g. ACP missing `options.entry`) |
| executor unbound | no in-box bind on docker |
| bake unsatisfied | bound external executor but no `image_layers` file |
| `unsupported executor` | not installed |

Recognition ≠ this host can run ≠ image baked.

## Checklist

```bash
uv run ageval plugin install plugins/my-mech
uv run ageval plugin list
uv run ageval executors
uv run ageval lock <dataset> --task <id> --profiles path/to/profiles.yaml
uv run ageval run <dataset> --task <id> --profiles path/to/profiles.yaml --probe
```
