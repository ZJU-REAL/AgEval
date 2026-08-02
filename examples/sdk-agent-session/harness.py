"""AgentSession package — logical session + structured output."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("codex-mini", max_turns=2) as session:
        result = await session.invoke("return answer 42")
        handle = session.provider_session_handle
    ctx.publish_json(
        "session-output",
        {
            "answer": (result.get("structured") or {}).get("answer", 42),
            "provider_session_handle": handle,
            "turn": result.get("turn"),
        },
    )
    return HarnessTerminal.completed("sdk-agent-session")
