"""executor-image-upstream — harness-scheduled ACP invoke."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


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
    package_dir = Path(__file__).resolve().parent
    prompt_path = package_dir / "prompts" / "agent.md"
    prompt = (
        prompt_path.read_text(encoding="utf-8").strip()
        if prompt_path.is_file()
        else 'Return ONLY JSON {"answer": 42}'
    )
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("pi-glm", actor_id="default", max_turns=1) as session:
        inv = await session.invoke(prompt)
    if not inv.get("ok"):
        return HarnessTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))
    payload = _answer_payload(dict(inv))
    if payload is None:
        return HarnessTerminal.failed("agent_output_missing_answer")
    ctx.publish_json("agent-output", payload)
    return HarnessTerminal.completed("executor-image-upstream")
