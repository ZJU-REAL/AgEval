"""container-per-group: two group targets, memory context across groups, final publish."""

from __future__ import annotations

from ageval_sdk import Agent, RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    models = ctx.params.get("models") or {}
    planner_profile = str(models.get("planner") or "planner")
    worker_profile = str(models.get("worker") or "worker")

    async with agent.session(
        planner_profile, actor_id="planner", max_turns=2
    ) as planner:
        plan = await planner.invoke(
            'Return ONLY JSON {"plan": "finalize", "seed": 40} with no other keys.'
        )
    if not plan.get("ok"):
        return RunTerminal.failed(plan.get("error") or "planner_failed")

    plan_struct = plan.get("structured") if isinstance(plan.get("structured"), dict) else {}
    seed = plan_struct.get("seed", 40)
    # Cross-group context via harness memory only (no cross-container RW).
    memory = f"Planner seed={seed}. Produce final answer 42."

    async with agent.session(
        worker_profile, actor_id="worker", max_turns=2
    ) as worker:
        out = await worker.invoke(
            f'{memory} Return ONLY JSON {{"answer": 42}} with no other keys.'
        )
    if not out.get("ok"):
        return RunTerminal.failed(out.get("error") or "worker_failed")

    structured = out.get("structured")
    if not isinstance(structured, dict) or "answer" not in structured:
        return RunTerminal.failed("agent_output_missing_answer")

    ctx.publish_json(
        "session-output",
        {
            "answer": structured.get("answer"),
            "mode": "container-per-group",
            "actors": ["planner", "worker"],
            "groups": ["analysis", "execution"],
            "cross_group_memory": True,
            "provider_session_handle": None,
        },
    )
    return RunTerminal.completed("multi-agent-container-per-group")
