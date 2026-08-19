"""record phase: collect, enrich, then the engine writes the trajectory.

Plugins may shape each turn's payload; only the engine writes the file, so a
plugin cannot quietly become the author of evidence. Both chains are fail-open:
a trajectory is observational, and losing shaping must not lose the Attempt.
"""

from __future__ import annotations

from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.evidence.invocation import read_invocation_payload
from ageval.evidence.trajectory import turn_rows, write_attempt_trajectory
from ageval.plugins.slots import TRAJECTORY_COLLECT, TRAJECTORY_ENRICH

PHASE = "record"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    turns: list[list[dict[str, Any]]] = []
    for directory in ctx.evidence.list_invocations():
        payload = read_invocation_payload(directory)
        shaped = await emit(ctx, TRAJECTORY_COLLECT, payload)
        shaped = await emit(ctx, TRAJECTORY_ENRICH, shaped)
        turns.append(turn_rows(**_fields(shaped, payload)))
    path = write_attempt_trajectory(
        ctx.evidence.root,
        turns,
        redaction_sentinels=ctx.evidence.sentinels,
    )
    ctx.record_fact("trajectory_recorded", {"turns": len(turns), "file": path.name})


def _fields(shaped: Any, original: dict[str, Any]) -> dict[str, Any]:
    """Accept a shaped payload only when it still carries the whole turn."""
    if isinstance(shaped, dict) and shaped.keys() >= original.keys():
        return {key: shaped[key] for key in original}
    return original
