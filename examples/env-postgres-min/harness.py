"""Env smoke: read parent-prepared environment fact + agent result."""

from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    env_path = ctx.workspace_root / ".bora_env_result.json"
    agent_path = ctx.workspace_root / ".bora_agent_result.json"
    if not env_path.is_file():
        return HarnessTerminal.failed("environment_result_missing")
    if not agent_path.is_file():
        return HarnessTerminal.failed("agent_result_missing")
    env = json.loads(env_path.read_text(encoding="utf-8"))
    agent = json.loads(agent_path.read_text(encoding="utf-8"))
    if not env.get("ok"):
        return HarnessTerminal.failed(env.get("error") or "environment_failed")
    ctx.publish_json(
        "env-result",
        {
            "status": agent.get("status") or agent.get("answer") or "ok",
            "env_action": env.get("action"),
            "query_ok": env.get("query_ok"),
            "rows": env.get("rows"),
        },
    )
    return HarnessTerminal.completed("env-postgres-min")
