"""Chain handlers for acp-oneshot (probe/install + trajectory)."""

from __future__ import annotations

from typing import Any

from acp_oneshot_plugin import PLUGIN_ID
from acp_oneshot_plugin.trajectory import SCHEMA, to_ageval_trajectory_events


def _executor_options(ctx: Any) -> dict[str, Any]:
    bindings = getattr(ctx, "bindings", None)
    winners = getattr(bindings, "winners", None) or {}
    winner = winners.get("executor") if isinstance(winners, dict) else None
    options = getattr(winner, "options", None) if winner is not None else None
    return dict(options or {})


def _api_key_locator(ctx: Any) -> str | None:
    lock = getattr(ctx, "lock", None)
    overlay = dict(getattr(lock, "job_overlay", None) or {})
    profiles = overlay.get("agent_profiles")
    profile_id = getattr(ctx, "profile_id", None)
    rows: list[Any] = []
    if isinstance(profiles, dict):
        if profile_id and profile_id in profiles:
            rows.append(profiles[profile_id])
        if "*" in profiles:
            rows.append(profiles["*"])
    elif isinstance(profiles, (list, tuple)):
        rows.extend(profiles)
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


async def ensure_runtime(ctx: Any, value: Any, nxt: Any) -> Any:
    """Probe then install the selected ACP entry inside the box.

    External plugin chains are not factories, so options come from the locked
    executor winner rather than bind-time closure.
    """
    options = _executor_options(ctx)
    from ageval.plugins.contrib.acp.hooks import ensure_runtime as acp_ensure

    handler = acp_ensure(options=options, api_key=_api_key_locator(ctx))
    return await handler(ctx, value, nxt)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Map wrapper dumps. Do not claim already-mapped foreign events."""
    del ctx
    out = await nxt(value)
    if not isinstance(out, dict):
        return out
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
