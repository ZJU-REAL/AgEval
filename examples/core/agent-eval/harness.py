"""Agent-eval harness: invoke parent Agent Service once (via launch agent_result).

In v0.6 the worker receives an optional precomputed agent_result from the parent
when the Agent Service completed a real Codex invocation before worker start
(single-shot projection). The Harness still only sees SDK context + result blob.
"""

from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    # Prefer parent-provided agent materialization (Agent Service path).
    agent_path = ctx.workspace_root / ".bora_agent_result.json"
    if not agent_path.is_file():
        return HarnessTerminal.failed("agent_result_missing")
    data = json.loads(agent_path.read_text(encoding="utf-8"))
    ctx.publish_json("agent-output", data)
    return HarnessTerminal.completed("agent-eval")
