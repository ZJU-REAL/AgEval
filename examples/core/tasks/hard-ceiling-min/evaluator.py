"""The ceiling held only if the invoke was refused and nothing was written."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    reply = json.loads(Path(inputs["artifacts"]["reply"]).read_text(encoding="utf-8"))
    wrote_anything = (Path(inputs["workspace_dir"]) / "answer.txt").exists()
    # Offline runs refuse for their own reason; both are refusals before the effect.
    refused = reply["ok"] is False and reply["error"] in {
        "agent_invocation_limit",
        "offline_forced",
    }
    held = refused and not wrote_anything
    return {
        "status": "PASS" if held else "FAIL",
        "score": 1.0 if held else 0.0,
        "metrics": {
            "refused_with": reply["error"],
            "agent_wrote_a_file": wrote_anything,
        },
    }
