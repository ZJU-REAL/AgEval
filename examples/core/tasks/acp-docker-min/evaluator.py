"""Judge the workspace against gold that only arrives in the evaluate phase."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    expected = (Path(inputs["evaluation_dir"]) / "expected.txt").read_text(encoding="utf-8").strip()
    answer = Path(inputs["workspace_dir"]) / "answer.txt"
    reply = json.loads(Path(inputs["artifacts"]["reply"]).read_text(encoding="utf-8"))
    setup_ran = (Path(inputs["workspace_dir"]) / ".setup-ran").is_file()
    # Gold is here now, and setup.sh already proved it was not there before.
    gold_late = (Path(inputs["evaluation_dir"]) / "expected.txt").is_file()

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
        "metrics": {
            "found": found[:100],
            "expected": expected,
            "agent_ok": reply["ok"],
            "setup_ran": setup_ran,
            "gold_arrived_at_evaluate": gold_late,
        },
    }
