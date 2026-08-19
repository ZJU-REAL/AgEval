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
    """Open the box, run the task, judge it, record it, tear the box down.

    A phase failure is an outcome, not a crash: it is recorded against the phase
    that failed and the Attempt still produces a result document. Cancellation
    (``BaseException``) still propagates, and cleanup still runs either way.
    """
    try:
        await environment.run(ctx)
        await run.run(ctx)
        await evaluate.run(ctx)
        await record.run(ctx)
    except Exception as exc:  # noqa: BLE001 — the phase name is the operator's answer
        ctx.record_fact(
            "phase_failed",
            {"phase": ctx.phase, "error": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        await cleanup.run(ctx)


__all__ = ["AttemptCtx", "run_attempt"]
