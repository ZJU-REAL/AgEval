from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["env-result"]).read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    label = rows[0].get("label") if rows and isinstance(rows[0], dict) else None
    ok = (
        data.get("query_ok") is True
        and data.get("env_action") == "query"
        and label == "ageval"
        and int(data.get("tool_calls") or 0) >= 1
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": data,
    }
