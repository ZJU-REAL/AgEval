# nooa — ecosystem executor plugin (NVIDIA OO Agents)

External `bora.plugin/1` package. **Not** first-party BORA core (only ACP is first-party).

This plugin binds BORA profiles to **[NVIDIA-labs OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents)**:

```python
from nooa.unifiedllm import get_llm_client
from nooa import Agent

llm = get_llm_client(model, api_base=base_url, api_key=secret)
agent = PackageAgent(llm=llm)
await agent.run(prompt, workdir=...)
```

Profile `base_url` + `api_key` (env locator) are projected into that client.
Package-local agents should subclass `nooa.Agent` and use generation methods (`...`).

Plain deterministic classes (e.g. slot-probe `FixedAnswerAgent`) still work without network.

## Install

Host needs the NVIDIA package:

```bash
uv sync --extra nooa          # or: pip install nooa
uv run bora plugin install plugins/nooa
```

Install updates `~/.bora/plugins` (or `$BORA_HOME/plugins`) only — **never** edits
`profiles.yaml` / `bora.yaml` / `task.yaml`.

## Bind

```yaml
bindings:
  solver:
    executor: nooa
    model: openai/glm-5.2
    api_key: litellm_api_key          # env locator
    # base_url: http://127.0.0.1:8000/v1   # optional; else litellm_base_url / OPENAI_BASE_URL
    options:
      agent: "lib.agents:JsonlAggAgent"   # package-local nooa.Agent
      method: "run"
```

## Journeys smoke (real API)

```bash
uv sync --extra nooa
uv run bora plugin install plugins/nooa
unset BORA_OFFLINE_AGENT
uv run bora run examples/journeys \
  --profiles examples/journeys/profiles.nooa.yaml
```

## Recognition ≠ Ready ≠ bind

- **install** → Recognition only (`plugin list` / executor visible)
- **profiles `executor: nooa`** → bind (+ model / base_url / api_key)
- **L1 Ready** → `image_contribute` bake installs `nooa` + `bora-executor-nooa` in the Attempt image; invoke is **docker exec** with projected credentials

## L1 Ready strategy

For Docker L1 tasks, nooa uses **in-container worker**. Parent does **not**
materialize package agents on the host for L1 success. See Dockerfile.bake + worker/.
