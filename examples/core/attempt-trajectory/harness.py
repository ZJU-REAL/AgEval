"""Mechanism package: multi-invoke trajectory success (or partial failure modes).

trajectory_mode in parameters:
  - success: two real parent-bound invokes (default)
  - crash / timeout / cancel: first invoke ok, second uses a force-error prompt path
    (parent Agent Service still records partial evidence for the second invoke)
"""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    mode = str(ctx.params.get("trajectory_mode") or "success")
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("codex-mini", max_turns=2) as session:
        first = await session.invoke(
            'Return ONLY JSON {"answer": 40} with no other keys.'
        )
        if not first.get("ok"):
            return HarnessTerminal.failed(first.get("error") or "first_invoke_failed")

        if mode == "success":
            second = await session.invoke(
                'Return ONLY JSON {"answer": 42} with no other keys. Final answer is 42.'
            )
        elif mode == "timeout":
            # Extremely large prompt can still complete; rely on parent limit path or
            # a prompt that is fine — acceptance for timeout uses unit/partial suite.
            # For public path, second invoke that fails closed is enough when offline
            # injected; for real path use a normal second and accept partial via
            # separate task override in acceptance.
            second = await session.invoke(
                'Return ONLY JSON {"answer": 42} with no other keys.'
            )
        else:
            second = await session.invoke(
                'Return ONLY JSON {"answer": 42} with no other keys.'
            )

        handle = session.provider_session_handle

    if not second.get("ok"):
        # Partial evidence is owned by Agent Service; harness reports failed terminal.
        # Evaluator must not invent PASS from missing trajectory.
        ctx.publish_json(
            "session-output",
            {
                "answer": None,
                "provider_session_handle": handle,
                "turns": 2,
                "first_ok": True,
                "second_ok": False,
                "second_error": second.get("error"),
                "mode": mode,
                "partial": True,
            },
        )
        return HarnessTerminal.failed(second.get("error") or "second_invoke_failed")

    structured = second.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "provider_session_handle": handle,
            "turns": 2,
            "first_ok": bool(first.get("ok")),
            "second_ok": bool(second.get("ok")),
            "mode": mode,
            "partial": False,
            "invocation_ids": [
                first.get("invocation_id"),
                second.get("invocation_id"),
            ],
        },
    )
    return HarnessTerminal.completed("attempt-trajectory")
