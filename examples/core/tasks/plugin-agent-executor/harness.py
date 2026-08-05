"""openai-http second backend — harness-scheduled invoke."""

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


def _load_prompt(package_dir: Path) -> str:
    p = package_dir / "prompts" / "agent.md"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return 'Return JSON {"answer": 42}'


async def run(ctx: HarnessContext) -> HarnessTerminal:
    package_dir = Path(__file__).resolve().parent
    prompt = _load_prompt(package_dir)
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("openai-mini", max_turns=1) as session:
        inv = await session.invoke(prompt)
    if not inv.get("ok"):
        return HarnessTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))
    payload = _answer_payload(dict(inv))
    if payload is None:
        return HarnessTerminal.failed("agent_output_missing_answer")
    ctx.publish_json("agent-output", payload)
    return HarnessTerminal.completed("plugin-agent-executor")
