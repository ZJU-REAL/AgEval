"""Independent evaluator for terminal-jsonl-agg aggregates structure + values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["artifacts"]["aggregates"])
    data = json.loads(path.read_text(encoding="utf-8"))
    expected_path = Path(__file__).resolve().parent / "evaluation" / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    ok = data == expected
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "exact_match": 1 if ok else 0,
            "has_users": int("top_5_users_by_amount" in data),
            "has_tags": int("top_5_tags_by_count" in data),
        },
    }
