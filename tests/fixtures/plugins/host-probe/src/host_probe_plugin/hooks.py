from __future__ import annotations

from typing import Any

from host_probe_plugin import PLUGIN_ID


async def image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    del ctx
    base = list(value) if isinstance(value, list) else []
    base.append({"plugin": PLUGIN_ID})
    return await nxt(base)
