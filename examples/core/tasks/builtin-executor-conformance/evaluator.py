from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["session-output"]).read_text(encoding="utf-8"))
    ok = data.get("answer") == 42 and data.get("provider_session_handle") is None
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "answer": data.get("answer"),
            "profile_id": data.get("profile_id"),
            "invocation_id": data.get("invocation_id"),
        },
    }
