---
name: bora-sdk-harness
description: Harness Core SDK usage — AgentSession, tools, terminals; what not to own.
---

# SDK / Harness

```python
from bora_sdk import Agent, HarnessContext, HarnessTerminal

async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("codex-mini", max_turns=2) as session:
        r = await session.invoke('Return ONLY JSON {"answer": 42}')
        if not r.get("ok"):
            return HarnessTerminal.failed(r.get("error") or "invoke_failed")
    ctx.publish_json("session-output", {"answer": r["structured"]["answer"]})
    return HarnessTerminal.completed("my-task")
```

## SDK may

- Open profile-bound sessions, invoke, call tools, publish artifacts, return terminal.

## SDK must not

- Decide final PASS
- Read host credentials
- Raise its own agent invocation limit
- Branch on Benchmark / task_id for Core behavior

## Trajectory

Parent Agent Service writes per-invoke evidence; harness `ctx.events` is optional supplement only.

Design: `docs/design/03-harness-layer.md`, `docs/design/04-harness-core-sdk.md`
