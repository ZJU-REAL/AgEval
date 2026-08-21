"""Independent evaluator for terminal-jsonl-agg (v1 terminal-bench class)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    arts = inputs.get("artifacts") or {}
    raw = arts.get("aggregates")
    if not raw:
        return {
            "status": "FAIL",
            "score": 0.0,
            "metrics": {"reason": "aggregates_missing"},
        }
    path = Path(str(raw))
    if not path.is_file():
        return {
            "status": "FAIL",
            "score": 0.0,
            "metrics": {"reason": "aggregates_missing"},
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    expected_raw = arts.get("expected")
    if expected_raw:
        expected = json.loads(Path(str(expected_raw)).read_text(encoding="utf-8"))
    else:
        gold = Path(str(inputs["evaluation_dir"])) / "expected.json"
        expected = json.loads(gold.read_text(encoding="utf-8"))
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
