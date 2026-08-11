"""Phase A nooa host smoke — harness only session.invoke (mechanism-agnostic)."""

from __future__ import annotations

import json
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


def _payload(inv: dict[str, Any]) -> dict[str, Any] | None:
    structured = inv.get("structured")
    if isinstance(structured, dict) and "answer" in structured:
        return structured
    text = str(inv.get("text") or "").strip()
    if not text:
        return None
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) and "answer" in val else None
    except json.JSONDecodeError:
        return None


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("nooa-solver", max_turns=1) as session:
        inv = await session.invoke('Return JSON {"answer": 42}')
    if not inv.get("ok"):
        return HarnessTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))
    payload = _payload(dict(inv))
    if payload is None:
        return HarnessTerminal.failed("agent_output_missing_answer")
    ctx.publish_json("agent-output", payload)
    return HarnessTerminal.completed("nooa-host-min")
