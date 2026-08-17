# builtin-executor-mixed

**Same Attempt, two profiles**, independent sessions and trajectory trees.

Harness opens `opencode-glm` then `pi-glm` (one invoke each). Both must succeed
with structured JSON.

## Profiles

| id | executor | model | notes |
| --- | --- | --- | --- |
| `opencode-glm` | `opencode` | `zai-coding-plan/glm-5.2` | OpenCode coding-plan route |
| `pi-glm` | `pi` | **`zai-coding-cn/glm-5.2`** | pi China Z.AI coding plan |

### How to run pi with 智谱 Coding Plan (do not skip)

pi does **not** use `base_url: .../api/anthropic` for this path. Built-in providers:

| Region | `--model` / profile `model` | Host env pi reads |
| --- | --- | --- |
| China coding plan | `zai-coding-cn/glm-5.2` | `ZAI_CODING_CN_API_KEY` |
| Global Z.AI | `zai/glm-5.2` | `ZAI_API_KEY` |

**Wrong:** `model: glm-5.2` alone → pi fuzzy-matches **OpenCode Zen** → wants
`OPENCODE_API_KEY` → `Invalid API key` if you pass a 智谱 coding key.

BORA `api_key: ${glm_coding_api_key}` projects that host env into
`ZAI_CODING_CN_API_KEY` / `ZAI_API_KEY` (and others) for the child process.

Host/repo `.env`:

```bash
glm_coding_api_key=...
```

## Run

```bash
uv run bora lock examples/core --task builtin-executor-mixed
uv run bora run  examples/core --task builtin-executor-mixed
```
