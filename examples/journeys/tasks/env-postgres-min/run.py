"""No Agent on this path: the task only records what it declared."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    ctx.publish_json("env-result", {"declared_sidecar": "db"})
    return RunTerminal.completed("env-postgres-min")
