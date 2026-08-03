from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["reducer-output"]).read_text(encoding="utf-8"))
    ok = (
        data.get("status") == "ok"
        and data.get("merged") is True
        and data.get("answer") == 42
        and data.get("env_query_ok") is True
        and data.get("turns") == 2
        and data.get("provider_session_handle") is None
    )
    return {"status": "PASS" if ok else "FAIL", "score": 1.0 if ok else 0.0, "metrics": data}
