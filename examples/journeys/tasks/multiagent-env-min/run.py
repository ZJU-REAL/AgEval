"""Multiagent + Environment — orchestration only.

Tools / diagnostics live under ``lib/``. Gold is only under ``evaluation/``.
Roles open independent ACP sessions (pi / opencode / grok-build) via profile ids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ageval_sdk import Agent, RunContext, RunTerminal
from lib.agent_json import agent_struct
from lib.db_tools import build_db_toolset, load_env_meta
from lib.diagnostics import ALLOWED_LABELS, SPECIALIST_SQL


def _role_profile(params: dict[str, Any], role: str, default: str) -> str:
    roles = params.get("roles") if isinstance(params.get("roles"), dict) else {}
    raw = roles.get(role) if isinstance(roles, dict) else None
    return str(raw or default)


async def run(ctx: RunContext) -> RunTerminal:
    package_dir = Path(__file__).resolve().parent
    params = ctx.params if isinstance(ctx.params, dict) else {}
    try:
        env = load_env_meta(package_dir, ctx.workspace_root)
    except (OSError, RuntimeError, json.JSONDecodeError, FileNotFoundError) as exc:
        return RunTerminal.failed(str(exc))

    specialist_profile = _role_profile(params, "specialist", "specialist")
    planner_profile = _role_profile(params, "planner", "planner")
    reducer_profile = _role_profile(params, "reducer", "reducer")

    tools = build_db_toolset(env)
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    findings: list[dict] = []

    # --- specialists (pi ACP): one session, multi-invoke ---
    async with agent.session(specialist_profile, max_turns=12) as specialist:
        for name, sql in SPECIALIST_SQL.items():
            obs = await tools.call("db_query", {"sql": sql})
            raw = obs.get("result") if isinstance(obs.get("result"), dict) else obs
            if obs.get("status") != "ok" or not isinstance(raw, dict) or not raw.get("ok"):
                return RunTerminal.failed(f"specialist_tool_failed:{name}:{obs}")
            rows = str(raw.get("stdout") or "")
            inv = await specialist.invoke(
                f"Specialist role: {name}. Allowed labels: {list(ALLOWED_LABELS)}.\n"
                f"Read-only SQL already executed:\n{sql}\n"
                f"ROWS (authoritative):\n{rows}\n"
                "Decide from ROWS only whether this specialty is active.\n"
                "Return ONLY compact JSON: "
                f'{{"specialist":"{name}","active":true|false,'
                f'"label":enum_or_null,"evidence":"short"}}.\n'
                "If ROWS do not support it: active=false, label=null. Never invent metrics."
            )
            if not inv.get("ok"):
                return RunTerminal.failed(inv.get("error") or f"specialist_failed:{name}")
            finding = agent_struct(inv) or {
                "specialist": name,
                "active": False,
                "label": None,
                "evidence": rows[:200],
                "parse_failed": True,
            }
            finding["tool_rows"] = rows[:400]
            findings.append(finding)

    # --- planner (opencode ACP): independent session ---
    async with agent.session(planner_profile, max_turns=2) as planner:
        plan_inv = await planner.invoke(
            "You are the **planner**. Here are specialist findings JSON:\n"
            + json.dumps(
                [{k: v for k, v in f.items() if k != "tool_rows"} for f in findings],
                ensure_ascii=False,
            )
            + "\nReturn ONLY JSON "
            '{"follow_up_sql": null or a single SELECT..., "rationale":"..."}.\n'
            "follow_up_sql must be null or a read-only SELECT. Do not list final labels."
        )
        if not plan_inv.get("ok"):
            return RunTerminal.failed(plan_inv.get("error") or "planner_failed")
        plan = agent_struct(plan_inv) or {}
        follow_sql = plan.get("follow_up_sql")
        follow_rows = ""
        if isinstance(follow_sql, str) and follow_sql.strip():
            fobs = await tools.call("db_query", {"sql": follow_sql.strip()})
            fraw = fobs.get("result") if isinstance(fobs.get("result"), dict) else fobs
            if isinstance(fraw, dict) and fraw.get("ok"):
                follow_rows = str(fraw.get("stdout") or "")

    # --- reducer (grok-build ACP): independent session ---
    async with agent.session(reducer_profile, max_turns=2) as reducer:
        red_inv = await reducer.invoke(
            "You are the **reducer**.\n"
            "Specialist findings:\n"
            + json.dumps(findings, ensure_ascii=False)
            + "\nPlanner follow-up rows (may be empty):\n"
            + (follow_rows or "(none)")
            + "\nReturn ONLY JSON with exactly three unique labels from "
            + str(list(ALLOWED_LABELS))
            + " that are best supported by the evidence: "
            '{"predicted_labels":["L1","L2","L3"],'
            '"supporting_specialists":["..."]}.\n'
            "Do not invent labels unsupported by tool_rows/evidence."
        )
        if not red_inv.get("ok"):
            return RunTerminal.failed(red_inv.get("error") or "reducer_failed")
        reduced = agent_struct(red_inv)
        if not isinstance(reduced, dict):
            return RunTerminal.failed("reducer_output_unstructured")
        labels = reduced.get("predicted_labels")
        if not isinstance(labels, list) or len(labels) != 3:
            return RunTerminal.failed("reducer_labels_invalid")
        if any(str(x) not in ALLOWED_LABELS for x in labels):
            return RunTerminal.failed("reducer_label_not_allowed")
        if len({str(x) for x in labels}) != 3:
            return RunTerminal.failed("reducer_labels_not_unique")

        ctx.publish_json(
            "reducer-output",
            {
                "predicted_labels": [str(x) for x in labels],
                "supporting_specialists": reduced.get("supporting_specialists") or [],
                "findings": findings,
                "planner": plan,
                "follow_up_rows": follow_rows,
                "profiles": {
                    "specialist": specialist_profile,
                    "planner": planner_profile,
                    "reducer": reducer_profile,
                },
                "provider_session_handle": None,
                "env_resource_id": env.get("resource_id"),
                "tool_calls": tools.side_effect_counter,
            },
        )
    return RunTerminal.completed("multiagent-env-min")
