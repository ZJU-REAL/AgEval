from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLD = "A"


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["answer"]).read_text(encoding="utf-8"))
    predicted = data.get("letter")
    ok = predicted == GOLD
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {"predicted": predicted, "gold": GOLD, "raw_chars": len(str(data.get("raw") or ""))},
    }
