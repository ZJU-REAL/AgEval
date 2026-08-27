"""run phase: hand control to the task's own ``run.py``, in a child process.

The control plane never imports task code. Agent invocations travel back over
the Agent Service socket, so the task gets a session without ever holding a
credential or the box handle.
"""

from __future__ import annotations

import inspect
from typing import Any

from ageval.attempt.artifact_harvest import harvest_workspace_artifacts
from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.plugins.slots import AFTER_RUN, BEFORE_RUN

PHASE = "run"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    ctx.assert_deadline()
    await emit(ctx, BEFORE_RUN)
    try:
        outcome = await _run_task_entry(ctx)
        ctx.record_fact("task_run", outcome)
        if not isinstance(outcome, dict) or outcome.get("ok") is not True:
            error = "task_run_failed"
            if isinstance(outcome, dict):
                error = str(outcome.get("error") or error)
            raise RuntimeError(error)
    finally:
        if ctx.agent_service is not None:
            await _seal_run_agent_service(ctx)
        # Solver writers cannot write after this point; evaluate may now start.
        # The Agent Service socket stays up so evaluator.py can still session().
        ctx.mark_writers_stopped()
    await harvest_workspace_artifacts(ctx)
    await emit(ctx, AFTER_RUN)


async def _run_task_entry(ctx: AttemptCtx) -> dict[str, object]:
    from ageval.runtime.task_launch import launch_task_worker

    return await launch_task_worker(ctx)


async def _seal_run_agent_service(ctx: AttemptCtx) -> None:
    seal = getattr(ctx.agent_service, "seal_run", None)
    if callable(seal):
        await _maybe_await(seal())
        return
    stop = getattr(ctx.agent_service, "stop", None)
    if stop is None:
        return
    await _maybe_await(stop())


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result
