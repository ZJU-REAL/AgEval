"""trajectory_collect handler for dsh."""

from __future__ import annotations

from typing import Any

from dsh_plugin import PLUGIN_ID


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Map native DSH dumps. Do not claim already-mapped foreign events."""
    del ctx
    out = await nxt(value)
    if not isinstance(out, dict):
        return out
    from dsh_plugin.trajectory import SCHEMA, to_ageval_trajectory_events

    events = out.get("events")
    if not isinstance(events, (list, tuple)) or not events:
        return out
    if all(isinstance(e, dict) and e.get("schema") == SCHEMA for e in events):
        if not any(e.get("source") == PLUGIN_ID for e in events if isinstance(e, dict)):
            return out
        meta = dict(out.get("metadata") or {})
        meta.setdefault("trajectory_source", PLUGIN_ID)
        return {**out, "metadata": meta}
    mapped = to_ageval_trajectory_events(tuple(e for e in events if isinstance(e, dict)))
    meta = dict(out.get("metadata") or {})
    meta.setdefault("trajectory_source", PLUGIN_ID)
    return {**out, "events": tuple(mapped), "metadata": meta}
