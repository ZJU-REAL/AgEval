from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["session-output"]).read_text(encoding="utf-8"))
    ok = data.get("ok") is True and data.get("first") is not None and data.get("second") is not None
    return {"status": "PASS" if ok else "FAIL", "score": 1.0 if ok else 0.0, "metrics": data}
