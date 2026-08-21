"""cleanup phase: the box always comes down.

``run_attempt`` calls this from ``finally``. A plugin may report on cleanup; no
plugin can skip it.
"""

from __future__ import annotations

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.plugins.slots import CLEANUP_REPORT

PHASE = "cleanup"


async def run(ctx: AttemptCtx) -> None:
    previous = ctx.phase
    ctx.phase = PHASE
    try:
        await ctx.host.stop(delete=not ctx.keep_workspace)
        ctx.record_fact("environment_stopped", {"deleted": not ctx.keep_workspace})
    except Exception as exc:  # noqa: BLE001 — cleanup failure is a warning, not a verdict
        ctx.record_fact(
            "cleanup_warning",
            {"error": f"{type(exc).__name__}: {exc}", "failed_phase": previous},
        )
    finally:
        await emit(ctx, CLEANUP_REPORT, ctx.facts_as_list())
