---
name: ageval-sdk-harness
description: >
  Write ageval package harness code with ageval_sdk (HarnessContext, Agent/AgentSession,
  ToolSet/AllowList/CallLimit, HarnessTerminal, publish artifacts). Use when implementing
  or reviewing harness.py, multi-invoke sessions, tool guards, terminals, or package-local
  tools. Triggers: "AgentSession", "HarnessTerminal", "ctx.publish_json", "ToolSet",
  "write harness", "max_turns", "session invoke". SDK must never decide PASS, hold host
  credentials, raise hard ceilings, or branch Core behavior on benchmark/task names.
---

# SDK / Harness

Install SDK with the monorepo (`uv sync`). Import:

```python
from ageval_sdk import (
    Agent,
    AgentSession,
    AllowList,
    CallLimit,
    HarnessContext,
    HarnessTerminal,
    Tool,
    ToolSet,
)
```

## Minimal harness

Profile **ids** come from package `agent_profiles` (coding agents bind
`executor: acp` + `- plugin: acp` / `options.entry` in Database profiles).
Harness only opens profiles by id — never
branches Core policy on entry/executor name.

```python
from ageval_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    profile = str(ctx.params.get("active_profile") or "opencode-acp")
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session(profile, max_turns=2) as session:
        first = await session.invoke('Return ONLY JSON {"answer": 40}')
        if not first.get("ok"):
            return HarnessTerminal.failed(first.get("error") or "first_failed")
        second = await session.invoke('Return ONLY JSON {"answer": 42}')
        if not second.get("ok"):
            return HarnessTerminal.failed(second.get("error") or "second_failed")
        structured = second.get("structured")
        if not isinstance(structured, dict) or "answer" not in structured:
            return HarnessTerminal.failed("agent_output_missing_answer")
    ctx.publish_json(
        "session-output",
        {
            "answer": structured["answer"],
            "provider_session_handle": session.provider_session_handle,
            "turns": 2,
        },
    )
    return HarnessTerminal.completed("my-task")
```

Entrypoint in yaml: `harness: entrypoint: harness:run` with `async def run(ctx)`.

Multi-role: open **separate** sessions with different profile ids (each profile
may bind a different executor / ACP `options.entry`). Writing a new executor
mechanism is `$ageval-plugin`, not this skill.

**Multi-task packages:** keep `tasks/*/harness.py` thin; put shared orchestration under
Dataset `shared/lib` and import `shared.lib.*` (see `ageval-config-package`).

## Ownership

| May | Must not |
| --- | --- |
| Open profile sessions, invoke, tools, publish artifacts | Decide final PASS |
| Use `ctx.params` | Re-read lock or host secrets |
| Return `completed` / `failed` terminal | Raise Core hard ceilings or isolation |
| Package-local business events | Be the only trajectory source |

Parent Agent Service writes observational `ageval.trajectory.event/1` into
`trajectory.jsonl`. `ctx.events` is an optional supplement only.

## Tools (local soft policy)

```python
from ageval_sdk import Tool, ToolSet, CallLimit, AllowList

ts = ToolSet(allowlist={"db_query"})
ts.add(Tool(name="db_query", fn=my_fn, schema={"required": ["sql"]}))
# CallLimit / AllowList for local soft guards — not Runtime hard ceilings
```

## Terminals

- `HarnessTerminal.completed(reason)` — harness finished work; **not** PASS
- `HarnessTerminal.failed(reason)` — harness failed; still not evaluator truth

Evaluator is a separate entrypoint process.

## Detail

- API surface: [references/api.md](references/api.md)
- Antipatterns: [references/antipatterns.md](references/antipatterns.md)
