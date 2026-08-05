"""Harness completes with wrong artifact — evaluator must FAIL."""

from __future__ import annotations

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    ctx.publish_json("agent-output", {"answer": 0, "note": "intentionally wrong"})
    return HarnessTerminal.completed("wrong-on-purpose")
