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
    delete = not ctx.keep_workspace
    errors: list[str] = []
    for host, fact in (
        (ctx.evaluate_host, "evaluate_host_stopped"),
        (ctx.host, "environment_stopped"),
    ):
        try:
            await _stop_host(ctx, host, fact=fact, delete=delete)
        except Exception as exc:  # noqa: BLE001 — cleanup failure is a warning, not a verdict
            errors.append(f"{type(exc).__name__}: {exc}")
    if errors:
        ctx.record_fact(
            "cleanup_warning",
            {"error": "; ".join(errors), "failed_phase": previous},
        )
    await emit(ctx, CLEANUP_REPORT, ctx.facts_as_list())


async def _stop_host(ctx: AttemptCtx, host: object | None, *, fact: str, delete: bool) -> None:
    if host is None:
        return
    if fact == "evaluate_host_stopped" and host is ctx.host:
        return
    stop = getattr(host, "stop", None)
    if stop is None:
        return
    await stop(delete=delete)
    ctx.record_fact(fact, {"deleted": delete})
