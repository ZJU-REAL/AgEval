"""Profile-only multi-executor conformance (no harness branching on backend)."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    profile_id = str(ctx.params.get("active_profile") or "codex-mini")
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session(profile_id, max_turns=1) as session:
        result = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys or prose.'
        )
        handle = session.provider_session_handle

    if not result.get("ok"):
        return HarnessTerminal.failed(result.get("error") or "invoke_failed")

    structured = result.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "profile_id": profile_id,
            "provider_session_handle": handle,
            "invocation_id": result.get("invocation_id"),
            "executor_error": result.get("error"),
        },
    )
    return HarnessTerminal.completed("builtin-executor-conformance")
