"""Multiagent + Environment — orchestration only.

Tools / diagnostics constants live under ``lib/``. Gold is only under ``evaluation/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from bora_sdk import Agent, HarnessContext, HarnessTerminal
from lib.agent_json import agent_struct
from lib.db_tools import build_db_toolset, load_env_meta
from lib.diagnostics import ALLOWED_LABELS, SPECIALIST_SQL


async def run(ctx: HarnessContext) -> HarnessTerminal:
    package_dir = Path(__file__).resolve().parent
    try:
        env = load_env_meta(package_dir, ctx.workspace_root)
    except (OSError, RuntimeError, json.JSONDecodeError, FileNotFoundError) as exc:
        return HarnessTerminal.failed(str(exc))

    tools = build_db_toolset(env)
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    findings: list[dict] = []

    # Multi-profile boundary (Spec 15): second profile for a short independent turn.
    async with agent.session("codex-reviewer", max_turns=1) as review:
        ping = await review.invoke(
            'Return ONLY JSON {"role":"reviewer","ready":true} with no prose.'
        )
        if not ping.get("ok"):
            return HarnessTerminal.failed(ping.get("error") or "reviewer_failed")

    async with agent.session("codex-mini", max_turns=12) as session:
        for name, sql in SPECIALIST_SQL.items():
            obs = await tools.call("db_query", {"sql": sql})
            raw = obs.get("result") if isinstance(obs.get("result"), dict) else obs
            if obs.get("status") != "ok" or not isinstance(raw, dict) or not raw.get("ok"):
                return HarnessTerminal.failed(f"specialist_tool_failed:{name}:{obs}")
            rows = str(raw.get("stdout") or "")
            inv = await session.invoke(
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
                return HarnessTerminal.failed(inv.get("error") or f"specialist_failed:{name}")
            finding = agent_struct(inv) or {
                "specialist": name,
                "active": False,
                "label": None,
                "evidence": rows[:200],
                "parse_failed": True,
            }
            finding["tool_rows"] = rows[:400]
            findings.append(finding)

        plan_inv = await session.invoke(
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
            return HarnessTerminal.failed(plan_inv.get("error") or "planner_failed")
        plan = agent_struct(plan_inv) or {}
        follow_sql = plan.get("follow_up_sql")
        follow_rows = ""
        if isinstance(follow_sql, str) and follow_sql.strip():
            fobs = await tools.call("db_query", {"sql": follow_sql.strip()})
            fraw = fobs.get("result") if isinstance(fobs.get("result"), dict) else fobs
            if isinstance(fraw, dict) and fraw.get("ok"):
                follow_rows = str(fraw.get("stdout") or "")

        red_inv = await session.invoke(
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
            return HarnessTerminal.failed(red_inv.get("error") or "reducer_failed")
        reduced = agent_struct(red_inv)
        if not isinstance(reduced, dict):
            return HarnessTerminal.failed("reducer_output_unstructured")
        labels = reduced.get("predicted_labels")
        if not isinstance(labels, list) or len(labels) != 3:
            return HarnessTerminal.failed("reducer_labels_invalid")
        if any(str(x) not in ALLOWED_LABELS for x in labels):
            return HarnessTerminal.failed("reducer_label_not_allowed")
        if len({str(x) for x in labels}) != 3:
            return HarnessTerminal.failed("reducer_labels_not_unique")

        ctx.publish_json(
            "reducer-output",
            {
                "predicted_labels": [str(x) for x in labels],
                "supporting_specialists": reduced.get("supporting_specialists") or [],
                "findings": findings,
                "planner": plan,
                "follow_up_rows": follow_rows,
                "provider_session_handle": session.provider_session_handle,
                "env_resource_id": env.get("resource_id"),
                "tool_calls": tools.side_effect_counter,
            },
        )
    return HarnessTerminal.completed("multiagent-env-min")
