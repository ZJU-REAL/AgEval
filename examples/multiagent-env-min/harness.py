"""Multiagent/env class: multi-invoke AgentSession + Attempt-local Postgres fact."""

from __future__ import annotations

import json

from bora_sdk import Agent, HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    env_path = ctx.workspace_root / ".bora_env_result.json"
    if not env_path.is_file():
        return HarnessTerminal.failed("environment_result_missing")
    env = json.loads(env_path.read_text(encoding="utf-8"))
    if not env.get("ok"):
        return HarnessTerminal.failed(env.get("error") or "environment_failed")

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("codex-mini", max_turns=2) as session:
        plan = await session.invoke(
            'You are planner. Return ONLY JSON {"plan":"query-smoke","steps":2}.'
        )
        reduce = await session.invoke(
            'You are reducer. Given plan steps=2 and env ready, '
            'Return ONLY JSON {"status":"ok","merged":true,"answer":42}.'
        )
    if not plan.get("ok"):
        return HarnessTerminal.failed(plan.get("error") or "planner_failed")
    if not reduce.get("ok"):
        return HarnessTerminal.failed(reduce.get("error") or "reducer_failed")
    structured = reduce.get("structured") if isinstance(reduce.get("structured"), dict) else {}
    ctx.publish_json(
        "reducer-output",
        {
            "status": structured.get("status") or "ok",
            "merged": bool(structured.get("merged")),
            "answer": structured.get("answer"),
            "env_query_ok": env.get("query_ok"),
            "env_rows": env.get("rows"),
            "turns": 2,
            "provider_session_handle": session.provider_session_handle,
        },
    )
    return HarnessTerminal.completed("multiagent-env-min")
