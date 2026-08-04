"""L1 ACP placement: two SDK invokes via parent client + docker exec entry."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("opencode-acp", actor_id="default", max_turns=2) as session:
        first = await session.invoke(
            'Return ONLY JSON {"answer": 40} with no other keys.'
        )
        second = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys. Final answer is 42.'
        )

    if not first.get("ok"):
        return HarnessTerminal.failed(str(first.get("error") or "first_invoke_failed"))
    if not second.get("ok"):
        return HarnessTerminal.failed(str(second.get("error") or "second_invoke_failed"))

    structured = second.get("structured")
    text2 = str(second.get("text") or "")
    answer = None
    if isinstance(structured, dict) and "answer" in structured:
        answer = structured.get("answer")
    elif "42" in text2:
        answer = 42

    if answer != 42:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": answer,
            "turns": 2,
            "actor_id": "default",
            "profile_id": "opencode-acp",
            "first_ok": bool(first.get("ok")),
            "second_ok": bool(second.get("ok")),
            "provider_session_handle": None,
        },
    )
    return HarnessTerminal.completed("acp-agent-placement")
