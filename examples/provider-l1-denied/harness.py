"""Negative: try to read evaluation/gold hidden material."""

from __future__ import annotations

from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    # Attempt to read evaluator-only material under package evaluation/
    candidates = [
        ctx.workspace_root / "evaluation" / "gold.json",
        Path("/attempt/package/evaluation/gold.json"),
    ]
    for p in candidates:
        try:
            if p.is_file():
                # Seeing gold is a security failure for this negative task.
                ctx.publish_json("probe", {"seen_gold": True, "path": str(p)})
                return HarnessTerminal.completed("leaked")
        except OSError:
            continue
    ctx.publish_json("probe", {"seen_gold": False})
    return HarnessTerminal.failed("workspace_view_denied")
