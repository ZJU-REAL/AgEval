"""shared-container multi-actor: two SDK sessions, memory handoff, final publish."""

from __future__ import annotations

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    models = ctx.params.get("models") or {}
    planner_profile = str(models.get("planner") or "planner")
    reviewer_profile = str(models.get("reviewer") or "reviewer")

    # Mid-loop collaboration uses Harness memory; shared_write (team/) is
    # enforced only inside the Agent container (shared GID), not on the host
    # harness workspace.

    async with agent.session(
        planner_profile, actor_id="planner", max_turns=2
    ) as planner:
        plan = await planner.invoke(
            'Return ONLY JSON {"plan": "sum", "value": 40} with no other keys.'
        )
    if not plan.get("ok"):
        return HarnessTerminal.failed(plan.get("error") or "planner_failed")

    plan_struct = plan.get("structured") if isinstance(plan.get("structured"), dict) else {}
    plan_value = plan_struct.get("value", 40)
    # Mid-loop memory (Scheme A): harness serializes into next prompt.
    memory_context = f"Planner said value={plan_value}. Reviewer: add 2."

    async with agent.session(
        reviewer_profile, actor_id="reviewer", max_turns=2
    ) as reviewer:
        review = await reviewer.invoke(
            f'{memory_context} Return ONLY JSON {{"answer": 42}} with no other keys.'
        )
    if not review.get("ok"):
        return HarnessTerminal.failed(review.get("error") or "reviewer_failed")

    structured = review.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        return HarnessTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "mode": "shared-container",
            "actors": ["planner", "reviewer"],
            "planner_ok": bool(plan.get("ok")),
            "reviewer_ok": bool(review.get("ok")),
            "memory_context_used": True,
            "provider_session_handle": None,
        },
    )
    return HarnessTerminal.completed("multi-agent-shared-container")
