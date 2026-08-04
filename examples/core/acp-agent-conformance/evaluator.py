"""Independent evaluator — PASS only from artifact facts, never ACP end_turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["session-output"]).read_text(encoding="utf-8"))
    inv1 = data.get("invoke_1") if isinstance(data.get("invoke_1"), dict) else {}
    inv2 = data.get("invoke_2") if isinstance(data.get("invoke_2"), dict) else {}
    inv3 = data.get("invoke_3") if isinstance(data.get("invoke_3"), dict) else {}
    ok1 = bool(inv1.get("ok"))
    ok2 = bool(inv2.get("ok"))
    ok3 = bool(inv3.get("ok"))

    # Turn1 or turn2 should carry answer JSON; prefer structured, else text.
    def _has_answer_n(inv: dict[str, Any], n: int) -> bool:
        s = inv.get("structured")
        if isinstance(s, dict) and s.get("answer") == n:
            return True
        text = str(inv.get("text") or "")
        return f'"answer"' in text and str(n) in text

    has_40 = _has_answer_n(inv1, 40)
    has_42 = _has_answer_n(inv2, 42) or "42" in str(inv3.get("text") or "")
    ok = ok1 and ok2 and ok3 and int(data.get("invokes") or 0) >= 3 and (has_40 or has_42)
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "profile_id": data.get("profile_id"),
            "ok1": ok1,
            "ok2": ok2,
            "ok3": ok3,
            "has_40": has_40,
            "has_42": has_42,
            "invokes": data.get("invokes"),
        },
    }
