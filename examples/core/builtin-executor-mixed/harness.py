"""Same Attempt, two profiles → independent sessions and trajectory trees."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("opencode-glm", max_turns=1) as s1:
        r1 = await s1.invoke('Return ONLY JSON {"n": 1}')
    async with agent.session("pi-glm", max_turns=1) as s2:
        r2 = await s2.invoke('Return ONLY JSON {"n": 2}')

    if not r1.get("ok"):
        return HarnessTerminal.failed(r1.get("error") or "opencode_glm_failed")
    if not r2.get("ok"):
        return HarnessTerminal.failed(r2.get("error") or "pi_glm_failed")

    ctx.publish_json(
        "session-output",
        {
            "ok": True,
            "first": r1.get("structured"),
            "second": r2.get("structured"),
            "ids": [r1.get("invocation_id"), r2.get("invocation_id")],
        },
    )
    return HarnessTerminal.completed("builtin-executor-mixed")
