"""Profile-only multi-executor conformance (no harness branching on backend)."""

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
    profile_id = str(ctx.params.get("active_profile") or "codex-mini")
    prompt_path = Path(__file__).resolve().parent / "prompts" / "agent.md"
    prompt = (
        prompt_path.read_text(encoding="utf-8").strip()
        if prompt_path.is_file()
        else 'Return ONLY JSON {"answer": 42} with no other keys or prose.'
    )
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session(profile_id, max_turns=1) as session:
        result = await session.invoke(prompt)
        handle = session.provider_session_handle

    if not result.get("ok"):
        return HarnessTerminal.failed(result.get("error") or "invoke_failed")

    payload = _answer_payload(dict(result))
    if payload is None:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": payload.get("answer"),
            "profile_id": profile_id,
            "provider_session_handle": handle,
            "invocation_id": result.get("invocation_id"),
            "executor_error": result.get("error"),
        },
    )
    return HarnessTerminal.completed("builtin-executor-conformance")
