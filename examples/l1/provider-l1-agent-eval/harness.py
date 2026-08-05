"""provider-l1-agent-eval — harness-scheduled Agent.session/invoke (Issue #5)."""

from __future__ import annotations

import json
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


def _params(ctx: HarnessContext) -> dict[str, Any]:
    raw = ctx.params
    return dict(raw) if isinstance(raw, dict) else {}


def _answer_payload(inv: dict[str, Any]) -> dict[str, Any] | None:
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
        pass
    start, end = text.rfind("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) and "answer" in val else None
        except json.JSONDecodeError:
            return None
    return None


async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = _params(ctx)
    models = params.get("models") if isinstance(params.get("models"), dict) else {}
    profile_id = str(models.get("default") or "codex-mini")
    question = str(params.get("question") or 'Return JSON {"answer": 42}')

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session(profile_id, actor_id="default", max_turns=1) as session:
        inv = await session.invoke(question)

    if not inv.get("ok"):
        return HarnessTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))

    payload = _answer_payload(dict(inv))
    if payload is None:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json("agent-output", payload)
    return HarnessTerminal.completed('provider-l1-agent-eval')
