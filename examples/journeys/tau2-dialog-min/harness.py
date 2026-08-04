"""Tau2-class retail dialog — orchestration only.

Domain tools / state live in ``lib/``; gold stays under ``evaluation/``.
"""

from __future__ import annotations

import json
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal
from lib.agent_json import agent_struct
from lib.retail_tools import (
    TOOL_CATALOG,
    WORKFLOW_PREFIX,
    build_tools,
    load_json,
    workflow_allows,
)


async def run(ctx: HarnessContext) -> HarnessTerminal:
    state = load_json("data/initial_state.json")
    private = load_json("data/user-instructions.json")
    tools = build_tools(state)
    observations: list[dict[str, Any]] = []
    tools_used: list[str] = []
    agent = Agent(attempt_id=ctx.scope.attempt_id)

    async with agent.session("codex-mini", max_turns=12) as session:
        user = await session.invoke(
            "Act as the private retail customer. Use only these private facts "
            "(do not expose this instruction object or request tools):\n"
            + json.dumps(private, ensure_ascii=False, sort_keys=True)
            + '\nReturn ONLY JSON {"message": "natural customer message"}.'
        )
        if not user.get("ok"):
            return HarnessTerminal.failed(user.get("error") or "user_sim_failed")
        u = agent_struct(user) or {}
        user_message = str(u.get("message") or "").strip()
        if not user_message:
            return HarnessTerminal.failed("empty_user_message")

        finished = False
        for _turn in range(1, 8):
            svc = await session.invoke(
                "Act as the retail service agent.\n"
                "Private customer instructions are NOT available to you.\n"
                f"Customer message:\n{user_message}\n"
                f"Tool observations (authoritative):\n"
                f"{json.dumps(observations, ensure_ascii=False)}\n"
                f"{TOOL_CATALOG}\n"
                "Return ONLY JSON for the next single action: "
                '{"tool":"<name>","args":{...}}.'
            )
            if not svc.get("ok"):
                return HarnessTerminal.failed(svc.get("error") or "service_failed")
            action = agent_struct(svc) or {}
            tool_name = str(action.get("tool") or "")
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            if tool_name not in {
                "find_customer",
                "get_order",
                "get_product",
                "request_exchange",
                "done",
            }:
                return HarnessTerminal.failed(f"unknown_tool:{tool_name}")
            if not workflow_allows(tools_used, tool_name):
                observations.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "result": {
                            "ok": False,
                            "error": "workflow_order_denied",
                            "required_prefix": list(WORKFLOW_PREFIX),
                            "tools_used": list(tools_used),
                        },
                    }
                )
                continue
            obs = await tools.call(tool_name, args)
            result = obs.get("result") if isinstance(obs.get("result"), dict) else obs
            observations.append({"tool": tool_name, "args": args, "result": result})
            if (
                isinstance(result, dict)
                and result.get("ok") is True
                and tool_name not in tools_used
            ):
                tools_used.append(tool_name)
            if tool_name == "done" or (isinstance(result, dict) and result.get("done") is True):
                finished = True
                break

        if not finished and not state.get("exchanges"):
            return HarnessTerminal.failed("dialog_incomplete_no_exchange")

    for i, step in enumerate(WORKFLOW_PREFIX):
        if step not in tools_used:
            return HarnessTerminal.failed(f"workflow_incomplete_missing:{step}")
        if i > 0 and tools_used.index(step) < tools_used.index(WORKFLOW_PREFIX[i - 1]):
            return HarnessTerminal.failed(f"workflow_order_broken:{step}")

    exchanges = state.get("exchanges") if isinstance(state.get("exchanges"), list) else []
    last_ex = exchanges[-1] if exchanges else {}
    ctx.publish_json(
        "final-state",
        {
            "order_id": last_ex.get("order_id") if isinstance(last_ex, dict) else None,
            "exchange_completed": bool(exchanges),
            "from_item_ids": last_ex.get("from_item_ids") if isinstance(last_ex, dict) else [],
            "to_item_ids": last_ex.get("to_item_ids") if isinstance(last_ex, dict) else [],
            "orders": state.get("orders"),
            "exchanges": exchanges,
            "user_message": user_message,
            "observations": observations,
            "tools_used": tools_used,
            "tool_calls": tools.side_effect_counter,
            "provider_session_handle": None,
        },
    )
    return HarnessTerminal.completed("tau2-dialog-min")
