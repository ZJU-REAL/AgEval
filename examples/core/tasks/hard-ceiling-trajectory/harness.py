"""Public ceiling probe: second invoke must be denied (agent_invocation_limit)."""

from __future__ import annotations

from ageval_sdk import Agent, RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("solver", max_turns=2) as session:
        first = await session.invoke('Return ONLY JSON {"n": 1}')
        second = await session.invoke('Return ONLY JSON {"n": 2}')

    # N+1 must fail closed with agent_invocation_limit (or wall) before external effect.
    second_err = second.get("error") if isinstance(second, dict) else None
    denied = not second.get("ok") and second_err in {
        "agent_invocation_limit",
        "wall_time_exceeded",
    }
    ctx.publish_json(
        "ceiling-output",
        {
            "first_ok": bool(first.get("ok")),
            "second_ok": bool(second.get("ok")),
            "second_error": second_err,
            "n_plus_one_denied": denied,
            "limit": 1,
        },
    )
    if not denied:
        return RunTerminal.failed(f"expected_limit_deny_got:{second_err}")
    # Harness completed the probe (denial is success of the negative mechanism).
    return RunTerminal.completed("hard-ceiling-trajectory")
