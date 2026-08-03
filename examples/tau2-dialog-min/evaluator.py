from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["final-state"]).read_text(encoding="utf-8"))
    ok = (
        data.get("status") == "resolved"
        and data.get("order_id") == "A1"
        and data.get("refund") is False
        and data.get("turns") == 2
        and data.get("provider_session_handle") is None
    )
    return {"status": "PASS" if ok else "FAIL", "score": 1.0 if ok else 0.0, "metrics": data}
