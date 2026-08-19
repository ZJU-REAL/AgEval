# sdk-agent-session

**AgentSession** multi-invoke smoke on the parent Agent Service.

The harness opens one session (`max_turns=2`), invokes twice, and publishes the
final structured answer. Evaluates that the second turn yields `answer == 42`,
both invokes succeeded, and the SDK session handle stays null (parent-bound).

## What you learn

- `ageval_sdk.Agent` + `session` multi-invoke API
- Same Attempt, multiple turns under one session budget
- Session is parent-bound — package code does not own provider credentials

## Requirements

- Codex (or configured executor) for profile `codex-mini`

## Run

```bash
uv run ageval lock examples/core --task sdk-agent-session
uv run ageval run  examples/core --task sdk-agent-session
```
