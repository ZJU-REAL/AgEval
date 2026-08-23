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

## Capabilities

| | Value |
| --- | --- |
| export | exclusive `executor` |
| inject | `environment`: `exec` |
| chain | `trajectory_collect` |
| bake | `docker/Dockerfile.bake` |

## Parameters

`options` merge: profile `options` then this plugin's `extensions` row (last wins).

| Name | Default | Purpose |
| --- | --- | --- |
| `options.step_limit` | `30` | Agent step cap. `0` = unlimited. Negative / non-int fail closed. |
| `options.cost_limit` | `0` | Cost cap. `0` = unlimited. Negative fail closed. |
| `options.cmd_timeout` | `30` | Seconds per `host.exec` bash action. |
| `model` | `openai/gpt-4o-mini` | LiteLLM model id on the parent. |
| `api_key` | `OPENAI_API_KEY` / `litellm_api_key` / `LITELLM_API_KEY` | Env **locator name** for the parent HTTP client. |
| `base_url` | `OPENAI_BASE_URL` / `litellm_base_url` / `LITELLM_BASE_URL` | OpenAI-compatible base (`api_base`). |

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

Same harness: `Agent.session(...).invoke`. Switch with `--profiles`. PASS stays
the package evaluator.
