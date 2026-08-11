"""Lifecycle emit helpers for L0/L1/L5 multi slots.

Application code calls these around prepare/run/evaluate/cleanup.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.middleware import run_chain
from bora.plugins.protocol import ExtensionGraph
from bora.plugins.slots import (
    AFTER_CLEANUP,
    AFTER_EVALUATE,
    AFTER_PREPARE,
    AFTER_RUN,
    BEFORE_CLEANUP,
    BEFORE_EVALUATE,
    BEFORE_PREPARE,
    BEFORE_RUN,
    CLEANUP_ACTIONS,
    CLEANUP_REPORT,
    IMAGE_CONTRIBUTE,
)


async def emit_phase(
    graph: ExtensionGraph,
    *,
    before_slot: str,
    after_slot: str,
    value: Any = None,
    ctx: Any = None,
) -> Any:
    mid = await run_chain(graph, before_slot, value, ctx=ctx)
    return await run_chain(graph, after_slot, mid, ctx=ctx)


async def emit_prepare(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_PREPARE, after_slot=AFTER_PREPARE, value=value, ctx=ctx
    )


async def emit_run(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_RUN, after_slot=AFTER_RUN, value=value, ctx=ctx
    )


async def emit_evaluate(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_EVALUATE, after_slot=AFTER_EVALUATE, value=value, ctx=ctx
    )


async def emit_cleanup(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Cleanup bookends + cleanup_actions/report (must not revoke score)."""
    mid = await emit_phase(
        graph, before_slot=BEFORE_CLEANUP, after_slot=AFTER_CLEANUP, value=value, ctx=ctx
    )
    mid = await run_chain(graph, CLEANUP_ACTIONS, mid, ctx=ctx)
    return await run_chain(graph, CLEANUP_REPORT, mid, ctx=ctx)


async def collect_image_contribute(
    graph: ExtensionGraph,
    *,
    ctx: Any = None,
) -> list[Any]:
    seed: list[Any] = []
    result = await run_chain(graph, IMAGE_CONTRIBUTE, seed, ctx=ctx)
    if isinstance(result, list):
        return result
    if result is None:
        return []
    return [result]
