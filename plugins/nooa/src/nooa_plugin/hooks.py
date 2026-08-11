"""Multi-slot on-handlers for nooa (image_contribute / trajectory_collect)."""

from __future__ import annotations

from typing import Any

from nooa_plugin.factory import PLUGIN_ID


async def image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    """Declare bake intent consumed by L1 prepare (Spec 05 Ready).

    install = Recognition only; this declare drives in-container worker bake.
    """
    del ctx
    declare = {
        "plugin": PLUGIN_ID,
        "bake": ["nooa", "bora-executor-nooa"],
        "ready_strategy": "in-container-worker",
        "worker": "bora-executor-nooa",
        "worker_path": "/usr/local/bin/bora-executor-nooa",
    }
    base = list(value) if isinstance(value, list) else []
    base.append(declare)
    return await nxt(base)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    del ctx
    return await nxt(value)
