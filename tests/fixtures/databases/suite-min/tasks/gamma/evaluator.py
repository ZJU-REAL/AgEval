from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["artifacts"]["result"])
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("ok") is True:
        return {"status": "PASS", "score": 1.0}
    return {"status": "FAIL", "score": 0.0}
