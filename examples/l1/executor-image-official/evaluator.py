from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["artifacts"]["agent-output"])
    data = json.loads(path.read_text(encoding="utf-8"))
    ok = data.get("answer") == 42
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {"answer": data.get("answer"), "image_path": "official"},
    }
