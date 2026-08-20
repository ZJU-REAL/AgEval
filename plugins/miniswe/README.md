# miniswe — mini-swe-agent executor plugin

External `ageval.plugin/1`. **Not** first-party ageval core.

Drives [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) as a
**host-loop**: the LLM client stays on the parent; every bash action goes
through the injected `environment` service (`host.exec`). This is **not** ACP.
Name is the mechanism (`miniswe`), not a benchmark.

```python
from minisweagent.agents.default import DefaultAgent
from minisweagent.models.litellm_model import LitellmModel

agent = DefaultAgent(LitellmModel(model_name=...), env)  # env calls host.exec
agent.run(prompt)
```

A kind that cannot `exec` fails at `ageval lock`, not mid-invoke. Model HTTP
stays on the parent. Credentials are locators projected into the parent HTTP
client; they never enter the lock.

## Install

```bash
uv sync --extra miniswe
uv run ageval plugin install plugins/miniswe
```

Install updates `$AGEVAL_HOME/plugins` only — never edits package yaml.

## Bind

```yaml
format: ageval.profiles/1
environment: docker
agent_profiles:
  solver:
    executor: miniswe
    extensions:
      - plugin: miniswe
        options:
          step_limit: 30          # 0 = unlimited
          cost_limit: 0           # 0 = unlimited
          cmd_timeout: 30
      - plugin: docker
    model: openai/glm-5.2
    api_key: ${litellm_api_key}
    base_url: ${litellm_base_url}
```

Same harness: `Agent.session(...).invoke`. Switch with `--profiles`.

## Slots

Exclusive `executor` plus `inject: environment` with `exec`. `trajectory_collect`
maps this plugin's events. `config.image_layers` is bake input for the
environment winner, not a timeline slot. PASS stays the package evaluator.
