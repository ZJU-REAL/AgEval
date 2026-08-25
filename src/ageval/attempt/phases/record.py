"""record phase: collect, enrich, seal, then summary_enrich.

Plugins may shape each turn's payload; the ``trajectory_seal`` winner writes
the file. Collect/enrich/summary_enrich are fail-open; losing the sealed file
fails the phase. ``summary_enrich`` runs once after a successful seal.
"""

from __future__ import annotations

from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.evidence.invocation import read_invocation_payload
from ageval.evidence.slim import slim_sealed_attempt
from ageval.evidence.trajectory import turn_rows
from ageval.plugins.binding import bind_winner
from ageval.plugins.slots import (
    SUMMARY_ENRICH,
    TRAJECTORY_COLLECT,
    TRAJECTORY_ENRICH,
    TRAJECTORY_SEAL,
)

PHASE = "record"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    turns: list[list[dict[str, Any]]] = []
    for directory in ctx.evidence.list_invocations():
        payload = read_invocation_payload(directory)
        shaped = await emit(ctx, TRAJECTORY_COLLECT, payload)
        shaped = await emit(ctx, TRAJECTORY_ENRICH, shaped)
        turns.append(turn_rows(**_fields(shaped, payload)))
    impl = bind_winner(ctx.registry, ctx.bindings, TRAJECTORY_SEAL)
    plugin_id = ctx.bindings.winners[TRAJECTORY_SEAL].plugin_id
    ctx.services.register(TRAJECTORY_SEAL, impl, plugin_id=plugin_id)
    path = impl.seal(ctx, turns)
    if not path.is_file():
        raise RuntimeError("trajectory_seal did not write the trajectory file")
    ctx.record_fact("trajectory_recorded", {"turns": len(turns), "file": path.name})
    if ctx.keep_vendor_raw:
        ctx.record_fact("vendor_raw_kept", {"keep_vendor_raw": True})
    else:
        slim_sealed_attempt(ctx.evidence.root)
        ctx.record_fact("vendor_raw_dropped", {"keep_vendor_raw": False})
    bag = await emit(ctx, SUMMARY_ENRICH, {})
    ctx.summary_extra = bag if isinstance(bag, dict) and bag else None


def _fields(shaped: Any, original: dict[str, Any]) -> dict[str, Any]:
    """Accept a shaped payload only when it still carries the whole turn."""
    if isinstance(shaped, dict) and shaped.keys() >= original.keys():
        return {key: shaped[key] for key in original}
    return original
