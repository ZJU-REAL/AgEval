from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent_path = ctx.workspace_root / ".bora_agent_result.json"
    if not agent_path.is_file():
        return HarnessTerminal.failed("agent_result_missing")
    data = json.loads(agent_path.read_text(encoding="utf-8"))
    ctx.publish_json("agent-output", data)
    return HarnessTerminal.completed("plugin-agent-executor")
