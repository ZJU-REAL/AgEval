"""Never executed by these tests: Config Core only reads the tree."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    ctx.publish_json("result", {"ok": True})
    return RunTerminal.completed()
