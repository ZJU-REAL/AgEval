"""Terminal-class L1 harness — explicit Agent.session/invoke (Issue #5).

Runtime seeds data/ into Attempt workspace and places agent effects in-container.
Harness owns scheduling: open session → invoke → read workspace file → publish.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora_sdk import Agent, HarnessContext, HarnessTerminal


def _parse_obj(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.rfind("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _params(ctx: HarnessContext) -> dict[str, Any]:
    raw = ctx.params
    return dict(raw) if isinstance(raw, dict) else {}


async def run(ctx: HarnessContext) -> HarnessTerminal:
    params = _params(ctx)
    models = params.get("models") if isinstance(params.get("models"), dict) else {}
    profile_id = str(models.get("default") or "terminal-pi")
    out_name = str(params.get("workspace_output") or "aggregates.json")
    out_path = Path(out_name)
    if out_path.is_absolute() or ".." in out_path.parts:
        return HarnessTerminal.failed("workspace_output_invalid")

    target = ctx.workspace_root / out_name
    # Isolation fixture may pre-seed solution/* into workspace (no Runtime Agent invoke).
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        ctx.publish_json("aggregates", data)
        return HarnessTerminal.completed("terminal-jsonl-agg")

    instruction_path = ctx.workspace_root / "instruction.md"
    if not instruction_path.is_file():
        return HarnessTerminal.failed("instruction_missing")
    instruction = instruction_path.read_text(encoding="utf-8")

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    # L1 implicit single-actor topology uses actor_id="default".
    async with agent.session(profile_id, actor_id="default", max_turns=1) as session:
        inv = await session.invoke(instruction)

    if not inv.get("ok"):
        return HarnessTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))

    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
    else:
        data = _parse_obj(inv.get("structured")) or _parse_obj(inv.get("text"))
        if data is None:
            return HarnessTerminal.failed("workspace_output_missing")

    ctx.publish_json("aggregates", data)
    return HarnessTerminal.completed("terminal-jsonl-agg")
