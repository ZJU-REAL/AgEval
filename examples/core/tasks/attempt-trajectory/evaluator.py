from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["session-output"]).read_text(encoding="utf-8"))
    # Trajectory presence is NOT a scoring input — only business answer contract.
    ok = (
        data.get("answer") == 42
        and data.get("provider_session_handle") is None
        and data.get("turns") == 2
        and data.get("first_ok") is True
        and data.get("second_ok") is True
        and data.get("partial") is not True
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "answer": data.get("answer"),
            "turns": data.get("turns"),
            "partial": data.get("partial"),
            "mode": data.get("mode"),
        },
    }
