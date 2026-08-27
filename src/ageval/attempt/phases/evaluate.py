"""evaluate phase: writers stop, gold arrives, evaluator decides.

Gold isolation here is a cut in *time*, not a mount trick: ``evaluation/`` is
uploaded at the start of this phase, so nothing the Agent could read ever had it
on disk. The verdict enters the Attempt exactly once, via ``bind_evaluation``.
The ``evaluation_runtime`` winner returns raw; it does not bind PASS.
"""

from __future__ import annotations

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.environments.protocol import ARTIFACTS_PATH, EVALUATION_PATH
from ageval.plugins.binding import bind_winner
from ageval.plugins.slots import AFTER_EVALUATE, BEFORE_EVALUATE, EVALUATION_RUNTIME

PHASE = "evaluate"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    ctx.assert_writers_stopped()  # solver writers; Agent Service may still be up
    await emit(ctx, BEFORE_EVALUATE)
    await _upload_task_artifacts(ctx)
    if ctx.evaluation_src is not None and ctx.evaluation_src.is_dir():
        await ctx.host.upload(ctx.evaluation_src, EVALUATION_PATH)
        ctx.record_fact("gold_materialized", {"at": PHASE})
    impl = bind_winner(ctx.registry, ctx.bindings, EVALUATION_RUNTIME)
    plugin_id = ctx.bindings.winners[EVALUATION_RUNTIME].plugin_id
    ctx.services.register(EVALUATION_RUNTIME, impl, plugin_id=plugin_id)
    result = await impl.evaluate(ctx)
    ctx.bind_evaluation(result)
    # Post-processing may annotate metrics; it may not change the verdict.
    status_before = str((result or {}).get("status") or "")
    after = await emit(ctx, AFTER_EVALUATE, result)
    if isinstance(after, dict) and str(after.get("status") or "") != status_before:
        raise RuntimeError("after_evaluate must not change the evaluation status")


async def _upload_task_artifacts(ctx: AttemptCtx) -> None:
    """The task published on this side; the evaluator judges inside the box."""
    staged = ctx.evidence.path("task-artifacts")
    if staged.is_dir() and any(staged.iterdir()):
        await ctx.host.upload(staged, ARTIFACTS_PATH)
        ctx.record_fact("artifacts_materialized", {"at": PHASE})
