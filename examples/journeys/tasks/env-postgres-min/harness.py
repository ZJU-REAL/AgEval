"""Env smoke — orchestration only; query tool lives in ``lib/``."""

from __future__ import annotations

import json
from pathlib import Path

from ageval_sdk import RunContext, RunTerminal
from lib.db_tools import build_db_toolset, load_env_meta


async def run(ctx: RunContext) -> RunTerminal:
    package_dir = Path(__file__).resolve().parent
    try:
        env = load_env_meta(package_dir, ctx.workspace_root)
    except (OSError, RuntimeError, json.JSONDecodeError, FileNotFoundError) as exc:
        return RunTerminal.failed(str(exc))

    tools = build_db_toolset(env)
    obs = await tools.call("db_query", {"sql": "SELECT label FROM smoke WHERE id = 1"})
    raw = obs.get("result") if isinstance(obs.get("result"), dict) else obs
    if obs.get("status") != "ok" or not isinstance(raw, dict) or not raw.get("ok"):
        return RunTerminal.failed(f"query_failed:{obs}")

    label = str(raw.get("stdout") or "").strip()
    ctx.publish_json(
        "env-result",
        {
            "status": "ok",
            "note": "env-ready",
            "env_action": "query",
            "query_ok": True,
            "rows": [{"label": label}],
            "tool_calls": tools.side_effect_counter,
            "seed_applied": env.get("seed_applied"),
        },
    )
    return RunTerminal.completed("env-postgres-min")
