# plugin-agent-executor

Second **executor mechanism** (`openai-http`) via harness-scheduled `Agent.session`/`invoke`.

Profile uses `executor: openai-http` (HTTP plugin path) instead of builtin Codex.
Harness only materializes parent agent result and publishes; evaluator requires
`answer == 42`.

## What you learn

- Non-builtin executors plug in by **mechanism name**, not by task-specific forks
- Package harness stays executor-agnostic
- Plugin / entry-point model is install + profile, not an app store

## Requirements

- OpenAI-compatible credentials / network for the configured model
- Plugin package for `openai-http` installed in the environment that runs ageval

## Run

```bash
uv run ageval lock examples/core --task plugin-agent-executor
uv run ageval run  examples/core --task plugin-agent-executor
```
