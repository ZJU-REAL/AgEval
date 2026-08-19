"""One Attempt, in order, in one place.

Read this file to know what happens and when. Each phase is a file under
``phases/``; inside a phase, ``emit(ctx, slot)`` runs the chain the lock already
ordered. Plugins change bindings — never this sequence.

Engine invariants live here, not in plugins: the lock and Attempt identity, the
deadline, ``cleanup`` always running, and PASS entering only through
``evaluate``.
"""

from __future__ import annotations

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.phases import cleanup, environment, evaluate, record, run


async def run_attempt(ctx: AttemptCtx) -> None:
    """Open the box, run the task, judge it, record it, tear the box down."""
    try:
        await environment.run(ctx)
        await run.run(ctx)
        await evaluate.run(ctx)
        await record.run(ctx)
    finally:
        await cleanup.run(ctx)


__all__ = ["AttemptCtx", "run_attempt"]
