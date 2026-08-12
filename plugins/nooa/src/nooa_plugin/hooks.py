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
    """Ensure payload.events are ``bora.trajectory.event/1`` with source=nooa."""
    del ctx
    out = await nxt(value)
    if not isinstance(out, dict):
        return out
    from nooa_plugin.trajectory import SCHEMA, to_bora_trajectory_events

    events = out.get("events")
    if not isinstance(events, (list, tuple)):
        return out
    if events and all(isinstance(e, dict) and e.get("schema") == SCHEMA for e in events):
        meta = dict(out.get("metadata") or {})
        meta.setdefault("trajectory_source", "nooa")
        return {**out, "metadata": meta}
    mapped = to_bora_trajectory_events(tuple(e for e in events if isinstance(e, dict)))
    meta = dict(out.get("metadata") or {})
    meta.setdefault("trajectory_source", "nooa")
    return {**out, "events": tuple(mapped), "metadata": meta}
