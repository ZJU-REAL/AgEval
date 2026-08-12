"""tau2 airline environment bridge (package-local; no Core adapter branching)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from shared.lib.paths import assets_root, package_root


def _load_tasks_raw() -> list[dict[str, Any]]:
    path = assets_root() / "tasks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tasks.json must be a list")
    return data


def load_task_dict(task_id: str) -> dict[str, Any]:
    for item in _load_tasks_raw():
        if str(item.get("id")) == str(task_id):
            return deepcopy(item)
    raise KeyError(f"unknown upstream task id: {task_id}")


def load_task_model(task_id: str):
    from tau2.data_model.tasks import Task

    return Task.model_validate(load_task_dict(task_id))


def make_environment():
    """Fresh airline Environment from ``shared/assets`` when present.

    Falls back to installed tau2 airline assets if package assets are missing.
    """
    from tau2.domains.airline.data_model import FlightDB
    from tau2.domains.airline.tools import AirlineTools
    from tau2.environment.environment import Environment

    assets = assets_root()
    db_path = assets / "db.json"
    policy_path = assets / "policy.md"
    # Task-local policy override (agent-visible data/, not gold).
    # Gold stays under evaluation/ only.

    if db_path.is_file() and policy_path.is_file():
        db = FlightDB.load(str(db_path))
        tools = AirlineTools(db)
        policy = policy_path.read_text(encoding="utf-8")
        return Environment(domain_name="airline", policy=policy, tools=tools)

    # Installed tau2 pin (v1.0.1)
    from tau2.domains.airline.environment import get_environment

    _ = package_root()  # keep helper used for future package-relative assets
    return get_environment()


def tool_catalog(env) -> str:
    lines: list[str] = []
    for t in env.get_tools():
        schema = getattr(t, "openai_schema", None)
        if schema:
            lines.append(json.dumps(schema, ensure_ascii=False))
        else:
            lines.append(f"- {t.name}: {getattr(t, 'short_desc', '')}")
    return "\n".join(lines)


def execute_tool_call(env, name: str, arguments: dict[str, Any], call_id: str):
    """Execute assistant tool; return tau2 ToolMessage."""
    from tau2.data_model.message import ToolCall

    tc = ToolCall(
        id=call_id or f"call_{name}",
        name=name,
        arguments=arguments or {},
        requestor="assistant",
    )
    return env.get_response(tc)


def load_eval_task(task_id: str, evaluation_task_json: Path):
    from tau2.data_model.tasks import Task

    if evaluation_task_json.is_file():
        return Task.model_validate(
            json.loads(evaluation_task_json.read_text(encoding="utf-8"))
        )
    return load_task_model(task_id)


def agent_facing_user_scenario(task_dict: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(task_dict.get("user_scenario") or {})


def format_user_scenario(scenario: dict[str, Any]) -> str:
    """Human-readable user-sim scenario (no evaluation gold)."""
    instr = scenario.get("instructions") or {}
    if not isinstance(instr, dict):
        return json.dumps(scenario, ensure_ascii=False, indent=2)
    parts = []
    if scenario.get("persona"):
        parts.append(f"Persona:\n{scenario['persona']}")
    for key, label in (
        ("known_info", "Known info"),
        ("reason_for_call", "Reason for call"),
        ("task_instructions", "Task instructions"),
        ("unknown_info", "Unknown info"),
    ):
        val = instr.get(key)
        if val:
            parts.append(f"{label}:\n{val}")
    return "\n\n".join(parts) if parts else json.dumps(scenario, ensure_ascii=False)
