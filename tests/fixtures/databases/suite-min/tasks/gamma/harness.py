from __future__ import annotations

import asyncio

from ageval_sdk import HarnessTerminal


async def run(ctx):
    sleep_ms = int(ctx.params.get("sleep_ms") or 0)
    if sleep_ms:
        await asyncio.sleep(sleep_ms / 1000.0)
    expect = ctx.params.get("expect_pass", True)
    ok = bool(expect) if not isinstance(expect, str) else expect.lower() == "true"
    payload = {"ok": ok, "task": "gamma"}
    ctx.publish_json("result", payload)
    return HarnessTerminal.completed()
