# hard-ceiling-trajectory

**Hard ceiling** probe: N+1 agent invoke must be denied **before** external effect.

Package limit is `agent_invocations: 1`. Harness attempts a second invoke; Runtime
must fail closed with `agent_invocation_limit` (or wall-time exceed). Evaluator
treats “second invoke denied after first ok” as the success condition of this
negative mechanism.

## What you learn

- Ceilings are enforced by Runtime / Provider, not by harness self-discipline
- Harness cannot raise its own invocation budget
- Denied invoke is recorded honestly; not rewritten into PASS by missing work

## Requirements

- Codex (or configured executor) for the first successful invoke

## Run

```bash
uv run ageval lock examples/core --task hard-ceiling-trajectory
uv run ageval run  examples/core --task hard-ceiling-trajectory
```
