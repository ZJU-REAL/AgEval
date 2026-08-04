"""L1 image-upstream: same harness contract as official path."""

from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    for candidate in (
        Path("/attempt/workspace/agent_result.json"),
        ctx.workspace_root / "agent_result.json",
    ):
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            ctx.publish_json("agent-output", data)
            return HarnessTerminal.completed("executor-image-upstream")
    return HarnessTerminal.failed("agent_result_missing")
