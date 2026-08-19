"""Minimal package harness for v0.5 HC-1 checkpoint."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    seed = ctx.params.get("seed", 0)
    message = ctx.params.get("message", "")
    ctx.publish_json(
        "result",
        {
            "seed": seed,
            "message": message,
            "attempt_id": ctx.scope.attempt_id,
        },
    )
    return RunTerminal.completed("harness-minimal ok")
