"""Terminal-class harness: publish Agent-written workspace file as artifact."""

from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    handoff = ctx.workspace_root / ".bora_workspace_output.json"
    if not handoff.is_file():
        return HarnessTerminal.failed("workspace_output_missing")
    data = json.loads(handoff.read_text(encoding="utf-8"))
    ctx.publish_json("aggregates", data)
    return HarnessTerminal.completed("workspace-file-eval")
