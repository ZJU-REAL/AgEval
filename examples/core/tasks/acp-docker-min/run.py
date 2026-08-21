"""One Agent session, one invoke. The workspace is where the work lands."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    async with ctx.agent.session("solver", max_turns=1) as session:
        reply = await session.invoke(ctx.params["instruction"])

    ctx.publish_json("reply", {"ok": bool(reply.get("ok")), "text": reply.get("text") or ""})
    if not reply.get("ok"):
        return RunTerminal.failed(str(reply.get("error") or "invoke_failed"))
    return RunTerminal.completed("acp-local-min")
