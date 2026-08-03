"""Evaluator for tool-guard package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["tool-trace"]).read_text(encoding="utf-8"))
    mode = data.get("mode")
    counter = data.get("side_effect_counter")
    obs = data.get("observations") or []
    if mode == "denied":
        ok = counter == 2 and len(obs) == 3 and obs[2].get("status") == "denied"
    else:
        ok = counter == 2 and len(obs) == 2 and all(o.get("status") == "ok" for o in obs)
    return {"status": "PASS" if ok else "FAIL", "score": 1.0 if ok else 0.0, "metrics": {"counter": counter}}
