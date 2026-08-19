"""Harness completes with wrong artifact — evaluator must FAIL."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    ctx.publish_json("agent-output", {"answer": 0, "note": "intentionally wrong"})
    return RunTerminal.completed("wrong-on-purpose")
