"""ACP conformance harness — multi-turn session for trajectory review.

Profile-only switch: harness never branches on entry/executor name.
Three invokes share one BORA AgentSession (and typically one ACP session_id).
"""

from __future__ import annotations

from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = ctx.params if isinstance(ctx.params, dict) else {}
    active = str(params.get("active_profile") or "opencode-acp")
    models = params.get("models") if isinstance(params.get("models"), dict) else {}
    profile_id = str(active or models.get("default") or "opencode-acp")

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    # max_turns=3: three user/assistant turns for turn-level trajectory review.
    async with agent.session(profile_id, max_turns=3) as session:
        r1 = await session.invoke(
            'Turn 1: Reply with only this JSON object and nothing else: {"answer": 40}'
        )
        r2 = await session.invoke(
            "Turn 2: Increment the previous answer by 2. "
            'Reply with only JSON {"answer": <n>} and nothing else.'
        )
        r3 = await session.invoke(
            "Turn 3: Confirm you still have session continuity. "
            "Reply in one short sentence mentioning the number 42."
        )

    if not r1.get("ok"):
        return HarnessTerminal.failed(str(r1.get("error") or "turn1_failed"))
    if not r2.get("ok"):
        return HarnessTerminal.failed(str(r2.get("error") or "turn2_failed"))
    if not r3.get("ok"):
        return HarnessTerminal.failed(str(r3.get("error") or "turn3_failed"))

    def _pack(r: Any) -> dict[str, Any]:
        return {
            "ok": bool(r.get("ok")),
            "text": str(r.get("text") or ""),
            "error": r.get("error"),
            "structured": r.get("structured")
            if isinstance(r.get("structured"), dict)
            else None,
            "invocation_id": r.get("invocation_id"),
        }

    ctx.publish_json(
        "session-output",
        {
            "profile_id": profile_id,
            "invoke_1": _pack(r1),
            "invoke_2": _pack(r2),
            "invoke_3": _pack(r3),
            "invokes": 3,
        },
    )
    return HarnessTerminal.completed("acp-agent-conformance")
