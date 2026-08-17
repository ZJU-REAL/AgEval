# miniswe — mini-swe-agent executor plugin

External `bora.plugin/1`. **Not** first-party BORA core.

Drives [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) on the
**parent host**. The Attempt container only runs `bash` via `docker exec`.
This is **not** ACP. Name is the mechanism (`miniswe`), not a benchmark.

```python
from minisweagent.agents.default import DefaultAgent
from minisweagent.models.litellm_model import LitellmModel

agent = DefaultAgent(LitellmModel(model_name=...), env)
agent.run(prompt)
```

L0: `env` is a local subprocess. L1: `bind_to_target` swaps in docker exec
against the Core-owned container (uid / workdir from `TargetPlacement`).
Model HTTP stays on the parent, so `provider.network: none` can still invoke.

## Install

```bash
uv sync --extra miniswe
uv run bora plugin install plugins/miniswe
```

Install updates `$BORA_HOME/plugins` only — never edits package yaml.

## Bind

```yaml
format: bora.profiles/1
bindings:
  solver:
    executor: miniswe
    extensions:
      - plugin: miniswe
        options:
          step_limit: 30          # 0 = unlimited
          cost_limit: 0           # 0 = unlimited
          cmd_timeout: 30
    model: openai/glm-5.2
    api_key: ${litellm_api_key}
    base_url: ${litellm_base_url}
```

Same harness: `Agent.session(...).invoke`. Switch with `--profiles`.

## Slots

`provide(executor)` + `on: image_contribute` + `on: trajectory_collect`.
Bake is nearly a no-op (bash already on `bora-attempt:l1`) but the file is
required for L1 bind. PASS stays the package evaluator.

## Evidence

`backend_raw/miniswe.json` is vendor-native. Layer B events use
`source: miniswe`. Do not claim `isolated` or anti-contamination from install.
