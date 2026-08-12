"""L1: single-actor ACP session; parent multi hooks still emit on host graph."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("probe-acp", actor_id="default", max_turns=1) as session:
        inv = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys. Final answer is 42.'
        )

    if not inv.get("ok"):
        return HarnessTerminal.failed(inv.get("error") or "invoke_failed")

    structured = inv.get("structured") if isinstance(inv.get("structured"), dict) else {}
    answer = structured.get("answer")
    # Best-effort parse from text if structured empty (some ACP paths).
    if answer is None:
        text = str(inv.get("text") or "")
        if '"answer"' in text and "42" in text:
            answer = 42

    ctx.publish_json(
        "probe-report",
        {
            "task": "l1-agent",
            "assurance": "l1",
            "invoke_ok": True,
            "answer": answer,
            "actor_id": "default",
            "text_preview": str(inv.get("text") or "")[:300],
        },
    )
    if answer != 42:
        return HarnessTerminal.failed(f"unexpected_answer:{answer}")
    return HarnessTerminal.completed("l1-agent")
