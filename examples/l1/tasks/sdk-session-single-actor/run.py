"""Phase 0: single-actor L1 SDK session — two invokes in attempt-container."""

from __future__ import annotations

from ageval_sdk import Agent, RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    # Implicit topology actor id is "default".
    async with agent.session("solver", actor_id="default", max_turns=2) as session:
        first = await session.invoke(
            'Return ONLY JSON {"answer": 40} with no other keys.'
        )
        second = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys. Final answer is 42.'
        )

    if not first.get("ok"):
        return RunTerminal.failed(first.get("error") or "first_invoke_failed")
    if not second.get("ok"):
        return RunTerminal.failed(second.get("error") or "second_invoke_failed")

    structured = second.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        return RunTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "turns": 2,
            "actor_id": "default",
            "first_ok": bool(first.get("ok")),
            "second_ok": bool(second.get("ok")),
            "provider_session_handle": None,
        },
    )
    return RunTerminal.completed("sdk-session-single-actor")
