"""Independent evaluator — PASS only from artifact facts, never ACP end_turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["session-output"]).read_text(encoding="utf-8"))
    inv1 = data.get("invoke_1") if isinstance(data.get("invoke_1"), dict) else {}
    inv2 = data.get("invoke_2") if isinstance(data.get("invoke_2"), dict) else {}
    ok1 = bool(inv1.get("ok"))
    ok2 = bool(inv2.get("ok"))
    structured = inv1.get("structured")
    has_answer = isinstance(structured, dict) and structured.get("answer") == 42
    if not has_answer:
        text1 = str(inv1.get("text") or "")
        has_answer = '"answer"' in text1 and "42" in text1
    ok = ok1 and ok2 and has_answer and int(data.get("invokes") or 0) >= 2
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "profile_id": data.get("profile_id"),
            "ok1": ok1,
            "ok2": ok2,
            "has_answer": has_answer,
            "invokes": data.get("invokes"),
        },
    }
