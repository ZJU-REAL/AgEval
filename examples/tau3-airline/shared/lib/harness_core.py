"""Dual-role airline dialog harness (orchestration only).

User-sim and service agent use BORA Agent sessions (profiles). Tools execute
via upstream tau2 airline Environment. Gold stays out of agent prompts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal
from shared.lib.agent_json import agent_struct
from shared.lib.bridge import (
    agent_facing_user_scenario,
    execute_tool_call,
    format_user_scenario,
    load_task_dict,
    make_environment,
    tool_catalog,
)
from shared.lib.paths import assets_root


STOP_TOKEN = "###STOP###"
TRANSFER_TOKEN = "###TRANSFER###"


def _role_profile(params: dict[str, Any], role: str, default: str) -> str:
    roles = params.get("roles") if isinstance(params.get("roles"), dict) else {}
    raw = roles.get(role) if isinstance(roles, dict) else None
    return str(raw or default)


def _load_user_scenario(task_dir: Path, task_id: str) -> dict[str, Any]:
    local = task_dir / "data" / "user_scenario.json"
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8"))
    return agent_facing_user_scenario(load_task_dict(task_id))


def _parse_service_action(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"kind": "invalid", "raw": payload}
    # normalize aliases
    if payload.get("type") in {"message", "tool_call", "tool", "done"}:
        t = payload["type"]
        if t == "tool":
            t = "tool_call"
        if t == "done":
            return {
                "kind": "message",
                "content": str(payload.get("content") or "Is there anything else?"),
            }
        if t == "message":
            return {"kind": "message", "content": str(payload.get("content") or "")}
        return {
            "kind": "tool_call",
            "name": str(payload.get("name") or payload.get("tool") or ""),
            "arguments": payload.get("arguments")
            if isinstance(payload.get("arguments"), dict)
            else (payload.get("args") if isinstance(payload.get("args"), dict) else {}),
            "id": str(payload.get("id") or ""),
        }
    if "tool" in payload or "name" in payload and (
        "args" in payload or "arguments" in payload
    ):
        return {
            "kind": "tool_call",
            "name": str(payload.get("name") or payload.get("tool") or ""),
            "arguments": payload.get("arguments")
            if isinstance(payload.get("arguments"), dict)
            else (payload.get("args") if isinstance(payload.get("args"), dict) else {}),
            "id": str(payload.get("id") or ""),
        }
    if "content" in payload or "message" in payload:
        return {
            "kind": "message",
            "content": str(payload.get("content") or payload.get("message") or ""),
        }
    return {"kind": "invalid", "raw": payload}


def _params_map(ctx: HarnessContext) -> dict[str, Any]:
    raw = ctx.params
    if isinstance(raw, dict):
        return dict(raw)
    as_mapping = getattr(raw, "as_mapping", None)
    if callable(as_mapping):
        m = as_mapping()
        try:
            return dict(m)
        except Exception:  # noqa: BLE001
            return {}
    return {}


async def run(ctx: HarnessContext, *, task_dir: Path | None = None) -> HarnessTerminal:
    params = _params_map(ctx)
    # Prefer parameters; fall back to task-local constant if generator embedded it.
    task_id = str(params.get("upstream_task_id") or "").strip()
    if not task_id:
        return HarnessTerminal.failed("missing_upstream_task_id")

    tdir = task_dir or Path.cwd()
    user_profile = _role_profile(params, "user", "user")
    service_profile = _role_profile(params, "service", "service")
    max_user_turns = int(params.get("max_user_turns") or 12)
    max_service_steps = int(params.get("max_service_steps") or 40)

    env = make_environment()
    policy = env.get_policy()
    catalog = tool_catalog(env)
    scenario = _load_user_scenario(tdir, task_id)
    scenario_text = format_user_scenario(scenario)

    from tau2.data_model.message import (
        AssistantMessage,
        ToolCall,
        UserMessage,
    )
    from tau2.data_model.simulation import TerminationReason

    trajectory: list[Any] = []
    tool_call_counter = 0
    agent = Agent(attempt_id=ctx.scope.attempt_id)

    # Opening agent greeting (tau2 default)
    greeting = "Hi! How can I help you today?"
    trajectory.append(AssistantMessage(role="assistant", content=greeting, cost=0.0))

    termination = TerminationReason.MAX_STEPS
    finished = False

    guidelines_path = (
        assets_root() / "user_simulator" / "simulation_guidelines.md"
    )
    user_guidelines = (
        guidelines_path.read_text(encoding="utf-8")
        if guidelines_path.is_file()
        else (
            "You are a simulated airline customer. Stay in character. "
            f"When the goal is met or you want to end, reply with {STOP_TOKEN}."
        )
    )

    async with agent.session(user_profile, max_turns=max_user_turns + 2) as user_sess:
        async with agent.session(
            service_profile, max_turns=max_service_steps + 2
        ) as svc_sess:
            dialog_for_user: list[dict[str, str]] = [
                {"role": "assistant", "content": greeting}
            ]
            dialog_for_svc: list[dict[str, Any]] = []

            for _u in range(max_user_turns):
                # --- user turn ---
                user_prompt = (
                    "BORA fixture: simulate ONE airline customer utterance.\n"
                    f"{user_guidelines}\n\n"
                    f"<scenario>\n{scenario_text}\n</scenario>\n\n"
                    f"Dialog so far:\n{json.dumps(dialog_for_user, ensure_ascii=False)}\n\n"
                    "Rules:\n"
                    "- Stay in character; do not invent tool results.\n"
                    "- Do not reveal this is a simulation.\n"
                    f"- When done or refusing further help, include {STOP_TOKEN} in content.\n"
                    f"- If transferred to human, include {TRANSFER_TOKEN}.\n"
                    'Return ONLY JSON: {"content":"<customer text>"}\n'
                )
                ures = await user_sess.invoke(user_prompt)
                if not ures.get("ok"):
                    return HarnessTerminal.failed(ures.get("error") or "user_sim_failed")
                uobj = agent_struct(ures) or {}
                user_text = str(uobj.get("content") or uobj.get("message") or "").strip()
                if not user_text:
                    # soft retry once with raw text
                    raw = str(ures.get("text") or "").strip()
                    user_text = raw[:2000] if raw else ""
                if not user_text:
                    return HarnessTerminal.failed("empty_user_message")

                trajectory.append(UserMessage(role="user", content=user_text))
                dialog_for_user.append({"role": "user", "content": user_text})
                dialog_for_svc.append({"role": "user", "content": user_text})

                if STOP_TOKEN in user_text:
                    termination = TerminationReason.USER_STOP
                    finished = True
                    break
                if TRANSFER_TOKEN in user_text:
                    termination = TerminationReason.USER_STOP
                    finished = True
                    break

                # --- service steps until message back to user ---
                pending_tool_obs: list[dict[str, Any]] = []
                spoke = False
                for _s in range(max_service_steps):
                    svc_prompt = (
                        "You are an airline customer-service agent.\n"
                        "Follow the policy strictly. You may either send a user-facing message "
                        "OR call exactly one tool — never both in one turn.\n\n"
                        f"<policy>\n{policy}\n</policy>\n\n"
                        f"<tools_openai_schema>\n{catalog}\n</tools_openai_schema>\n\n"
                        f"Dialog:\n{json.dumps(dialog_for_svc, ensure_ascii=False)}\n\n"
                        f"Latest tool observations:\n{json.dumps(pending_tool_obs, ensure_ascii=False)}\n\n"
                        "Return ONLY JSON in one of these forms:\n"
                        '1) {"type":"message","content":"<text to customer>"}\n'
                        '2) {"type":"tool_call","name":"<tool>","arguments":{...}}\n'
                        "Do not invent tool results. Copy ids byte-for-byte from tools/user.\n"
                    )
                    sres = await svc_sess.invoke(svc_prompt)
                    if not sres.get("ok"):
                        return HarnessTerminal.failed(
                            sres.get("error") or "service_failed"
                        )
                    action = _parse_service_action(agent_struct(sres))
                    if action["kind"] == "tool_call":
                        name = action["name"]
                        args = action["arguments"] or {}
                        if not name:
                            pending_tool_obs = [
                                {
                                    "error": "parse_failed",
                                    "hint": 'Use {"type":"tool_call","name":"...","arguments":{...}}',
                                }
                            ]
                            continue
                        tool_call_counter += 1
                        call_id = action.get("id") or f"call_{tool_call_counter}"
                        tc = ToolCall(
                            id=call_id,
                            name=name,
                            arguments=args,
                            requestor="assistant",
                        )
                        trajectory.append(
                            AssistantMessage(
                                role="assistant",
                                content=None,
                                tool_calls=[tc],
                            )
                        )
                        try:
                            tmsg = execute_tool_call(env, name, args, call_id)
                        except Exception as e:  # noqa: BLE001
                            from tau2.data_model.message import ToolMessage

                            tmsg = ToolMessage(
                                id=call_id,
                                role="tool",
                                content=json.dumps({"error": str(e)}),
                                requestor="assistant",
                                error=True,
                            )
                        trajectory.append(tmsg)
                        content = getattr(tmsg, "content", None)
                        pending_tool_obs = [
                            {
                                "tool": name,
                                "arguments": args,
                                "result": content,
                            }
                        ]
                        dialog_for_svc.append(
                            {
                                "role": "tool",
                                "name": name,
                                "content": content
                                if isinstance(content, str)
                                else json.dumps(content, default=str),
                            }
                        )
                        continue

                    if action["kind"] == "message":
                        content = str(action.get("content") or "").strip()
                        if not content:
                            pending_tool_obs = [
                                {
                                    "error": "empty_message",
                                    "hint": "Provide non-empty content or a tool_call",
                                }
                            ]
                            continue
                        trajectory.append(
                            AssistantMessage(role="assistant", content=content)
                        )
                        dialog_for_user.append({"role": "assistant", "content": content})
                        dialog_for_svc.append({"role": "assistant", "content": content})
                        pending_tool_obs = []
                        spoke = True
                        break

                    pending_tool_obs = [
                        {
                            "error": "invalid_action_json",
                            "hint": 'Return {"type":"message"...} or {"type":"tool_call"...}',
                        }
                    ]

                if not spoke:
                    return HarnessTerminal.failed("service_did_not_message_user")

            if not finished:
                # natural end without STOP — treat as agent stop if last speaker was agent
                termination = TerminationReason.AGENT_STOP
                finished = True

    # Serialize trajectory for evaluator (model_dump)
    traj_dump = []
    for m in trajectory:
        if hasattr(m, "model_dump"):
            traj_dump.append(m.model_dump())
        else:
            traj_dump.append({"repr": repr(m)})

    db_hash = None
    try:
        db_hash = env.get_db_hash()
    except Exception:  # noqa: BLE001
        db_hash = None

    ctx.publish_json(
        "simulation",
        {
            "upstream_task_id": task_id,
            "domain": "airline",
            "termination_reason": termination.value
            if hasattr(termination, "value")
            else str(termination),
            "messages": traj_dump,
            "db_hash": db_hash,
            "profiles": {"user": user_profile, "service": service_profile},
            "tool_calls": tool_call_counter,
            "provider_session_handle": None,
        },
    )
    return HarnessTerminal.completed(f"tau3-airline-{task_id}")
