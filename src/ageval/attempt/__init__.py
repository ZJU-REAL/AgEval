"""One Attempt, in order, in one place.

Read this file to know what happens and when. Each phase is a file under
``phases/``; inside a phase, ``emit(ctx, slot)`` runs the chain the lock already
ordered. Plugins change bindings — never this sequence.

Engine invariants live here, not in plugins: the lock and Attempt identity, the
deadline, ``cleanup`` always running, and PASS entering only through
``evaluate``.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.phases import cleanup, environment, evaluate, record, run

Phase = Callable[[AttemptCtx], Awaitable[None]]


async def run_attempt(ctx: AttemptCtx) -> None:
    """Open the box, run the task, judge it, record it, tear the box down.

    A phase failure is an outcome, not a crash: it is recorded against the phase
    that failed and the Attempt still produces a result document. Cancellation
    (``BaseException``) still propagates, and cleanup still runs either way.
    """
    try:
        for phase in (environment.run, run.run, evaluate.run, record.run):
            await _timed(ctx, phase)
    except Exception as exc:  # noqa: BLE001 — the phase name is the operator's answer
        ctx.record_fact(
            "phase_failed",
            {"phase": ctx.phase, "error": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        await _timed(ctx, cleanup.run)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _timed(ctx: AttemptCtx, phase: Phase) -> None:
    """Run one phase and record how long it took (observational only)."""
    started_mono = time.monotonic()
    started_at = _utc_now()
    try:
        await phase(ctx)
    finally:
        ctx.record_fact(
            "phase_finished",
            {
                "phase": ctx.phase,
                "duration_ms": round((time.monotonic() - started_mono) * 1000.0, 3),
                "started_at": started_at,
                "finished_at": _utc_now(),
            },
        )


__all__ = ["AttemptCtx", "run_attempt"]
