"""Minimal package harness for v0.5 HC-1 checkpoint."""

from __future__ import annotations

from ageval_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
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
    return HarnessTerminal.completed("harness-minimal ok")
