from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["deny-output"]).read_text(encoding="utf-8"))
    both = (
        data.get("denied_before_mutation") is True
        and data.get("mutation_executed") is False
        and bool(data.get("unknown_action_error"))
        and bool(data.get("dangerous_sql_error"))
    )
    return {
        "status": "PASS" if both else "FAIL",
        "score": 1.0 if both else 0.0,
        "metrics": data,
    }
