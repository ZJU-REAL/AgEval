"""Judge the workspace, not the reply: PASS only if the file is really there."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    expected = str(inputs["parameters"]["expected"]).strip()
    answer = Path(inputs["workspace_dir"]) / "answer.txt"
    reply = json.loads(Path(inputs["artifacts"]["reply"]).read_text(encoding="utf-8"))

    if not answer.is_file():
        return {
            "status": "FAIL",
            "score": 0.0,
            "metrics": {"reason": "answer.txt missing", "agent_ok": reply["ok"]},
        }
    found = answer.read_text(encoding="utf-8").strip()
    passed = found == expected
    return {
        "status": "PASS" if passed else "FAIL",
        "score": 1.0 if passed else 0.0,
        "metrics": {"found": found[:100], "expected": expected, "agent_ok": reply["ok"]},
    }
