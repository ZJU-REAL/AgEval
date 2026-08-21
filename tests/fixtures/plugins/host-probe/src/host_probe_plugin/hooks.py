from __future__ import annotations

from typing import Any

from host_probe_plugin import PLUGIN_ID


async def mark_ready(ctx: Any, value: Any, nxt: Any) -> Any:
    """Record that this plugin saw the box become ready."""
    record = getattr(ctx, "record_fact", None)
    if callable(record):
        record("host_probe_ready", {"plugin": PLUGIN_ID})
    return await nxt(value)
