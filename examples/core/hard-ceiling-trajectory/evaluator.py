from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["ceiling-output"]).read_text(encoding="utf-8"))
    # Only typed hard-ceiling errors count (not offline short-circuit).
    ok = data.get("n_plus_one_denied") is True and data.get("second_error") in {
        "agent_invocation_limit",
        "wall_time_exceeded",
    }
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": data,
    }
