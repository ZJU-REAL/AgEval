from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Evaluator-only truth: goal spec is re-declared here, independent of harness params.
GOAL: dict[str, str] = {'mug': 'desk'}


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["trace"]).read_text(encoding="utf-8"))
    locations = data.get("final_locations") or {}
    ok = all(locations.get(obj) == dest for obj, dest in GOAL.items())
    steps = data.get("steps") or []
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "goal": GOAL,
            "final_locations": {k: locations.get(k) for k in GOAL},
            "n_steps": len(steps),
            "n_noop": sum(1 for s in steps if not s.get("cmd")),
        },
    }
