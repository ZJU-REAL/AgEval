"""PASS only when the sidecar answered from inside the box."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    probe_path = Path(inputs["workspace_dir"]) / "db-probe.json"
    if not probe_path.is_file():
        return {"status": "FAIL", "score": 0.0, "metrics": {"reason": "setup left no probe"}}
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    reachable = probe.get("reachable") is True
    return {
        "status": "PASS" if reachable else "FAIL",
        "score": 1.0 if reachable else 0.0,
        "metrics": {
            "sidecar": probe.get("service"),
            "reachable": reachable,
            "error": probe.get("error"),
        },
    }
