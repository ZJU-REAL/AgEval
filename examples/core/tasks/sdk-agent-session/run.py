"""AgentSession package — two real parent-bound invokes, null provider handle."""

from __future__ import annotations

from ageval_sdk import Agent, RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("solver", max_turns=2) as session:
        first = await session.invoke(
            'Return ONLY JSON {"answer": 40} with no other keys.'
        )
        second = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys. Final answer is 42.'
        )
        handle = session.provider_session_handle

    if not first.get("ok"):
        return RunTerminal.failed(first.get("error") or "first_invoke_failed")
    if not second.get("ok"):
        return RunTerminal.failed(second.get("error") or "second_invoke_failed")

    structured = second.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        # Accept text parse best-effort if structured missing but text has JSON.
        return RunTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "provider_session_handle": handle,
            "turns": 2,
            "first_ok": bool(first.get("ok")),
            "second_ok": bool(second.get("ok")),
        },
    )
    return RunTerminal.completed("sdk-agent-session")
