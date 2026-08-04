"""ACP conformance harness — profile-only switch, no entry/vendor branches."""

from __future__ import annotations

from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = ctx.params if isinstance(ctx.params, dict) else {}
    active = str(params.get("active_profile") or "opencode-acp")
    models = params.get("models") if isinstance(params.get("models"), dict) else {}
    profile_id = str(active or models.get("default") or "opencode-acp")

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session(profile_id, max_turns=2) as session:
        r1 = await session.invoke(
            'Reply with only this JSON object and nothing else: {"answer": 42}'
        )
        r2 = await session.invoke("Confirm you can continue this session. Reply briefly.")

    if not r1.get("ok"):
        return HarnessTerminal.failed(str(r1.get("error") or "first_invoke_failed"))
    if not r2.get("ok"):
        return HarnessTerminal.failed(str(r2.get("error") or "second_invoke_failed"))

    ctx.publish_json(
        "session-output",
        {
            "profile_id": profile_id,
            "invoke_1": {
                "ok": bool(r1.get("ok")),
                "text": str(r1.get("text") or ""),
                "error": r1.get("error"),
                "structured": r1.get("structured")
                if isinstance(r1.get("structured"), dict)
                else None,
            },
            "invoke_2": {
                "ok": bool(r2.get("ok")),
                "text": str(r2.get("text") or ""),
                "error": r2.get("error"),
            },
            "invokes": 2,
        },
    )
    return HarnessTerminal.completed("acp-agent-conformance")
