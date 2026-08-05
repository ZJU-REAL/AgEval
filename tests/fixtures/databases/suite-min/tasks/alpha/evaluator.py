from __future__ import annotations
from typing import Any

def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    raw = inputs.get("result")
    if isinstance(raw, dict) and raw.get("ok") is True:
        return {"status": "PASS", "score": 1.0}
    return {"status": "FAIL", "score": 0.0}
