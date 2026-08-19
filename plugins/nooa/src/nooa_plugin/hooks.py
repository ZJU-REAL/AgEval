"""Multi-slot on-handlers for nooa (image_contribute / trajectory_collect)."""

from __future__ import annotations

from typing import Any

from nooa_plugin.factory import PLUGIN_ID


async def image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    """Declare this plugin on the image_contribute chain (L1 Ready).

    install = Recognition only. Core bakes ``docker/Dockerfile.bake`` if present.
    """
    del ctx
    declare = {
        "plugin": PLUGIN_ID,
    }
    base = list(value) if isinstance(value, list) else []
    base.append(declare)
    return await nxt(base)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Map native nooa dumps. Do not claim already-mapped foreign events."""
    del ctx
    out = await nxt(value)
    if not isinstance(out, dict):
        return out
    from nooa_plugin.trajectory import SCHEMA, to_ageval_trajectory_events

    events = out.get("events")
    if not isinstance(events, (list, tuple)) or not events:
        return out
    if all(isinstance(e, dict) and e.get("schema") == SCHEMA for e in events):
        if not any(e.get("source") == "nooa" for e in events if isinstance(e, dict)):
            return out
        meta = dict(out.get("metadata") or {})
        meta.setdefault("trajectory_source", "nooa")
        return {**out, "metadata": meta}
    mapped = to_ageval_trajectory_events(tuple(e for e in events if isinstance(e, dict)))
    meta = dict(out.get("metadata") or {})
    meta.setdefault("trajectory_source", "nooa")
    return {**out, "events": tuple(mapped), "metadata": meta}
