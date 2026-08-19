"""Multi-slot handlers: real effects + audit — not declaration DSL rows."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from slot_probe.audit import audit, probe_dir

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
POST_SETUP = PLUGIN_ROOT / "scripts" / "post_setup.sh"


async def before_agent_open(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("before_agent_open")
    return await nxt(value)


async def after_agent_open(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_open")
    return await nxt(value)


async def before_agent_invoke(ctx: Any, value: Any, nxt: Any) -> Any:
    if isinstance(value, str):
        value = value + "\n[slot-probe]"
    audit("before_agent_invoke", prompt_len=len(value) if isinstance(value, str) else None)
    return await nxt(value)


async def after_agent_invoke(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_invoke", ok=bool(getattr(value, "ok", None)))
    return await nxt(value)


async def normalize_agent_result(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    meta = getattr(out, "metadata", None)
    if isinstance(meta, dict):
        meta = dict(meta)
        meta["slot_probe_normalized"] = True
        try:
            out.metadata = meta
        except Exception:
            pass
    audit("normalize_agent_result")
    return out


async def before_agent_close(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("before_agent_close")
    return await nxt(value)


async def after_agent_close(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_close")
    return await nxt(value)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        md = dict(out.get("metadata") or {})
        md.setdefault("trajectory_source", "slot-probe")
        out = {**out, "metadata": md}
    audit("trajectory_collect")
    return out


async def trajectory_enrich(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        md = dict(out.get("metadata") or {})
        md["slot_probe"] = "v1"
        md["slot_probe_enrich"] = True
        out = {**out, "metadata": md}
    audit("trajectory_enrich")
    return out


async def cleanup_report(ctx: Any, value: Any, nxt: Any) -> Any:
    """Audit that cleanup reported, without being able to prevent it."""
    audit(ctx, "cleanup_report")
    return await nxt(value)
