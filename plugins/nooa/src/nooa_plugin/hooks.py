"""Multi-slot on-handlers for nooa (image_contribute / trajectory_collect)."""

from __future__ import annotations

from typing import Any

from nooa_plugin.factory import PLUGIN_ID


async def image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    """Declare bake intent; L1 host-in-container does not require image bake."""
    del ctx
    declare = {
        "plugin": PLUGIN_ID,
        "bake": ["nooa", "bora-executor-nooa"],
        "ready_strategy": "host-in-container",
    }
    base = list(value) if isinstance(value, list) else []
    base.append(declare)
    return await nxt(base)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    del ctx
    return await nxt(value)
