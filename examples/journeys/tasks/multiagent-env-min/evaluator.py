"""Independent evaluator: reducer labels must match seeded ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["reducer-output"]).read_text(encoding="utf-8"))
    expected_path = Path(__file__).resolve().parent / "evaluation" / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    pred = data.get("predicted_labels")
    if not isinstance(pred, list):
        return {"status": "FAIL", "score": 0.0, "metrics": {"reason": "missing_labels"}}
    pred_set = {str(x) for x in pred}
    exp_set = {str(x) for x in expected.get("predicted_labels") or []}
    # Exactly three unique labels matching gold set (order-insensitive).
    ok = (
        len(pred) == 3
        and len(pred_set) == 3
        and pred_set == exp_set
        and data.get("provider_session_handle") is None
        and int(data.get("tool_calls") or 0) >= 5  # five specialist probes at minimum
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "predicted": sorted(pred_set),
            "expected": sorted(exp_set),
            "tool_calls": data.get("tool_calls"),
            "findings_count": len(data.get("findings") or []),
        },
    }
