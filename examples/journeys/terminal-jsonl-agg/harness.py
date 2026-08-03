"""Terminal-class L1 harness — production path runs inside Docker (run_l1).

This module remains the package entrypoint for L0 fallback; L1 orchestrator
uses an in-container publish script with the same contract.
"""

from __future__ import annotations

import json

from bora_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    # L0-only fallback: parent materializes .bora_workspace_output.json.
    handoff = ctx.workspace_root / ".bora_workspace_output.json"
    if handoff.is_file():
        data = json.loads(handoff.read_text(encoding="utf-8"))
        ctx.publish_json("aggregates", data)
        return HarnessTerminal.completed("terminal-jsonl-agg")
    # Prefer direct workspace file when L1 mounted workspace is visible to worker.
    direct = ctx.workspace_root / "aggregates.json"
    if direct.is_file():
        data = json.loads(direct.read_text(encoding="utf-8"))
        ctx.publish_json("aggregates", data)
        return HarnessTerminal.completed("terminal-jsonl-agg")
    return HarnessTerminal.failed("workspace_output_missing")
