"""Spec 06 named SDK path: ToolSet AllowList / CallLimit soft policy."""

from __future__ import annotations

import asyncio

from bora_sdk import AllowList, CallLimit, Tool, ToolSet


def test_call_limit_denies_third_without_side_effect() -> None:
    ts = ToolSet(allowlist=AllowList.of("echo"), call_limit=CallLimit(max_calls=2))
    ts.add(Tool(name="echo", fn=lambda a: a.get("t")))

    async def _run() -> None:
        assert (await ts.call("echo", {"t": "a"}))["status"] == "ok"
        assert (await ts.call("echo", {"t": "b"}))["status"] == "ok"
        denied = await ts.call("echo", {"t": "c"})
        assert denied["status"] == "denied"
        assert denied["reason"] == "call_limit"
        assert ts.side_effect_counter == 2

    asyncio.run(_run())


def test_allowlist_denies_unknown_tool() -> None:
    ts = ToolSet(allowlist=AllowList.of("echo"))
    ts.add(Tool(name="echo", fn=lambda a: "x"))
    ts.add(Tool(name="other", fn=lambda a: "y"))

    async def _run() -> None:
        denied = await ts.call("other", {})
        assert denied["status"] == "denied"
        assert denied["reason"] == "allowlist"

    asyncio.run(_run())
