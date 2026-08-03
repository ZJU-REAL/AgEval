"""Tau2-class multi-turn dialog: two AgentSession turns, sealed final state."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("codex-mini", max_turns=2) as session:
        turn1 = await session.invoke(
            'Retail dialog turn 1. Return ONLY JSON {"intent":"lookup_order","order_id":"A1"}.'
        )
        turn2 = await session.invoke(
            'Retail dialog turn 2. Given intent lookup_order, '
            'Return ONLY JSON {"status":"resolved","order_id":"A1","refund":false}.'
        )
    if not turn1.get("ok") or not turn2.get("ok"):
        return HarnessTerminal.failed(
            (turn1.get("error") if not turn1.get("ok") else turn2.get("error")) or "dialog_failed"
        )
    s2 = turn2.get("structured") if isinstance(turn2.get("structured"), dict) else {}
    ctx.publish_json(
        "final-state",
        {
            "status": s2.get("status"),
            "order_id": s2.get("order_id"),
            "refund": s2.get("refund"),
            "turns": 2,
            "provider_session_handle": session.provider_session_handle,
        },
    )
    return HarnessTerminal.completed("tau2-dialog-min")
