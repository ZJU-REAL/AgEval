"""Terminal-class L1 harness — explicit Agent.session/invoke (Issue #5).

Runtime seeds data/ into Attempt workspace and places agent effects in-container.
Harness owns scheduling: open session → invoke → read workspace file → publish.
"""

from __future__ import annotations

import json
from pathlib import Path

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    # RunParameterView supports dotted get — do not coerce via dict().
    models = ctx.params.get("models") if isinstance(ctx.params.get("models"), dict) else {}
    # Prefer allowlisted CLI override, then package models.default.
    profile_id = str(ctx.params.get("active_profile") or models.get("default") or "solver")
    out_name = str(ctx.params.get("workspace_output") or "aggregates.json")
    out_path = Path(out_name)
    if out_path.is_absolute() or ".." in out_path.parts:
        return RunTerminal.failed("workspace_output_invalid")

    target = ctx.workspace_root / out_name
    # Isolation fixture may pre-seed solution/* into workspace (no Runtime Agent invoke).
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        ctx.publish_json("aggregates", data)
        return RunTerminal.completed("terminal-jsonl-agg")

    instruction_path = ctx.workspace_root / "instruction.md"
    if not instruction_path.is_file():
        return RunTerminal.failed("instruction_missing")
    instruction = instruction_path.read_text(encoding="utf-8")

    async with ctx.agent.session(profile_id, max_turns=1) as session:
        inv = await session.invoke(instruction)

    if not inv.get("ok"):
        return RunTerminal.failed(str(inv.get("error") or "agent_invoke_failed"))

    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        ctx.publish_json("aggregates", data)
        return RunTerminal.completed("terminal-jsonl-agg")

    # Remote boxes (e2b / daytona / ssh) do not share this disk. Chat text is
    # not the artifact — Runtime harvests artifacts.publishable after writers
    # stop via host.download.
    return RunTerminal.completed("terminal-jsonl-agg")
