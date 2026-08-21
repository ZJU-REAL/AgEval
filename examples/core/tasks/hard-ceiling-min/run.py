"""Ask for an invoke the ceiling forbids, and report what came back."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    async with ctx.agent.session("solver", max_turns=1) as session:
        reply = await session.invoke(ctx.params["instruction"])

    ctx.publish_json("reply", {"ok": bool(reply.get("ok")), "error": reply.get("error")})
    return RunTerminal.failed(str(reply.get("error") or "invoke_refused"))
