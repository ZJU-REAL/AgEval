"""Score the rematerialized workspace. Marker package must be absent here."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(inputs.get("workspace_dir") or ""))
    if workspace.is_dir() and (workspace / "answer.txt").is_file():
        answer = (workspace / "answer.txt").read_text(encoding="utf-8").strip()
    else:
        answer = ""
    leaked = (workspace / "target" / "leak.so").exists()
    oracle_present = importlib.util.find_spec("ageval_agent_oracle") is not None
    ok = answer == "42" and not leaked and not oracle_present
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "answer": answer,
            "leaked": leaked,
            "oracle_present": oracle_present,
        },
    }
