"""v1-like echo-contract harness: publish structured agent result as answer."""

from __future__ import annotations

import json

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    agent_path = ctx.workspace_root / ".bora_agent_result.json"
    if not agent_path.is_file():
        return HarnessTerminal.failed("agent_result_missing")
    data = json.loads(agent_path.read_text(encoding="utf-8"))
    # Accept either exact echo object or nested fields from model variance.
    if isinstance(data, dict) and "echo" in data:
        payload = {"echo": data["echo"]}
    else:
        return HarnessTerminal.failed("echo_field_missing")
    ctx.publish_json("answer", payload)
    return HarnessTerminal.completed("echo-contract")
