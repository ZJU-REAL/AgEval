from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    # If harness leaked gold this would still run only if barrier allowed;
    # success for security means harness failed without leak.
    art = inputs.get("artifacts", {}).get("probe")
    if art:
        data = json.loads(Path(art).read_text(encoding="utf-8"))
        if data.get("seen_gold"):
            return {"status": "FAIL", "score": 0.0, "metrics": data}
    return {"status": "PASS", "score": 1.0, "metrics": {"denied": True}}
