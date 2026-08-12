"""Multi-slot middleware chain: serial next(), may rewrite value; omit next = short-circuit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from bora.plugins.protocol import ExtensionGraph, HandlerRef, NextFn


async def run_chain(
    graph: ExtensionGraph,
    slot: str,
    value: Any,
    *,
    ctx: Any = None,
) -> Any:
    """Run multi handlers for *slot* in priority order (lower first)."""
    handlers = graph.chain(slot)
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
    # Build from the end so first handler (lowest priority number) runs outermost first.
    for href in reversed(list(handlers)):
        next_fn = _wrap(href, next_fn, ctx=ctx)
    return await next_fn(value)


def _wrap(href: HandlerRef, nxt: NextFn, *, ctx: Any) -> NextFn:
    handler = href.handler

    async def _call(value: Any) -> Any:
        # Support async and sync callables; also plain pass-through objects.
        if callable(handler):
            result = handler(ctx, value, nxt)
            if hasattr(result, "__await__"):
                return await result  # type: ignore[no-any-return]
            return result
        # Non-callable contribution (e.g. image declare dict): pass through.
        return await nxt(value)

    return _call


async def passthrough_handler(_ctx: Any, value: Any, nxt: NextFn) -> Any:
    """Default no-op middleware used by builtin defaults."""
    return await nxt(value)


def sync_passthrough_factory(**_kwargs: Any) -> Callable[..., Awaitable[Any]]:
    return passthrough_handler
