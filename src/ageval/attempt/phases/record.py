"""record phase: collect, enrich, then the engine writes the trajectory.

Plugins may shape events; only the engine writes the sealed file, so a plugin
cannot quietly become the author of evidence.
"""

from __future__ import annotations

from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.plugins.slots import TRAJECTORY_COLLECT, TRAJECTORY_ENRICH

PHASE = "record"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    for invocation in _invocations(ctx):
        events = await emit(ctx, TRAJECTORY_COLLECT, invocation)
        events = await emit(ctx, TRAJECTORY_ENRICH, events)
        _seal(ctx, events)
    ctx.record_fact("trajectory_recorded", {"invocations": len(_invocations(ctx))})


def _invocations(ctx: AttemptCtx) -> list[dict[str, Any]]:
    lister = getattr(ctx.evidence, "list_invocations", None)
    if lister is None:
        return []
    return [{"path": str(path)} for path in lister()]


def _seal(ctx: AttemptCtx, events: Any) -> None:
    """Engine-owned write. The Agent Service already sealed per-invocation files."""
    if not isinstance(events, dict):
        return
    ctx.record_fact("trajectory_sealed", {"invocation": str(events.get("path") or "")})
