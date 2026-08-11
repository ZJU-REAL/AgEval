from __future__ import annotations
from typing import Any

async def before_invoke(ctx: Any, value: Any, nxt: Any) -> Any:
    return await nxt(value)
