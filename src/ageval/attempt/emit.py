"""Chain slot execution.

A chain is onion middleware: each handler gets ``(ctx, value, nxt)`` and may
rewrite the value, short-circuit by not awaiting ``nxt``, or raise. Ordering
came from the lock, not from runtime discovery.

Failure policy is per slot: reporting slots are fail-open (recorded, stepped
over); everything on the critical path fails its phase.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ageval.plugins.protocol import HandlerRef, NextFn
from ageval.plugins.slots import is_fail_open, is_slot


async def emit(ctx: Any, slot: str, value: Any = None) -> Any:
    """Run the locked chain for *slot* and return the (possibly rewritten) value."""
    if not is_slot(slot):
        from ageval.plugins.errors import UnknownExtensionSlotError

        raise UnknownExtensionSlotError(
            f"unknown extension slot: {slot!r}",
            kind="unknown_extension_slot",
        )
    handlers = ctx.bindings.chain(slot) if ctx.bindings is not None else []
    if not handlers:
        return value
    if is_fail_open(slot):
        return await _run_fail_open(ctx, slot, handlers, value)
    return await run_handlers(handlers, value, ctx=ctx)


async def _run_fail_open(
    ctx: Any,
    slot: str,
    handlers: Sequence[HandlerRef],
    value: Any,
) -> Any:
    """Reporting chains never take the Attempt down; the failure is recorded."""
    try:
        return await run_handlers(handlers, value, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 — declared fail-open slot
        record = getattr(ctx, "record_fact", None)
        if callable(record):
            record(
                "slot_failed_open",
                {"slot": slot, "error": f"{type(exc).__name__}: {exc}"},
            )
        return value


async def run_chain(graph: Any, slot: str, value: Any, *, ctx: Any = None) -> Any:
    """Run one chain slot from an already-resolved graph.

    Used by hosts that hold the graph directly (Agent Service session path)
    rather than an ``AttemptCtx``.
    """
    handlers = graph.chain(slot) if graph is not None else []
    return await run_handlers(handlers, value, ctx=ctx)


async def run_handlers(
    handlers: Sequence[HandlerRef],
    value: Any,
    *,
    ctx: Any = None,
) -> Any:
    """Execute an ordered handler list as onion middleware."""
    if not handlers:
        return value

    async def _tail(v: Any) -> Any:
        return v

    next_fn: NextFn = _tail
    for href in reversed(list(handlers)):
        next_fn = _wrap(href, next_fn, ctx=ctx)
    return await next_fn(value)


def _wrap(href: HandlerRef, nxt: NextFn, *, ctx: Any) -> NextFn:
    handler = href.handler

    async def _call(value: Any) -> Any:
        result = handler(ctx, value, nxt)
        if hasattr(result, "__await__"):
            return await result
        return result

    return _call
