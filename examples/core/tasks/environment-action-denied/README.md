# environment-action-denied

**Expected-failure** env probe: undeclared / dangerous environment actions are
denied **before mutation**.

No Agent profiles. Runtime runs a deny probe against the package Environment
(PostgreSQL resource class). Harness reads `.ageval_env_result.json`, asserts
`denied_before_mutation`, and publishes the denial record for evaluation.

## What you learn

- Environment actions are capability-gated, not free-form shell from harness
- Fail closed: unknown or dangerous SQL must not mutate state
- Env handoff meta is how the package observes Runtime decisions

## Requirements

- Local Docker / env manager able to stand up the package’s PostgreSQL resource

## Run

```bash
uv run ageval lock examples/core --task environment-action-denied
uv run ageval run  examples/core --task environment-action-denied
```
