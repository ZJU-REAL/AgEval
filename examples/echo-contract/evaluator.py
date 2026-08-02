"""Exact-match evaluator (v1 echo-contract semantics)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["artifacts"]["answer"])
    data = json.loads(path.read_text(encoding="utf-8"))
    ok = data == {"echo": "BORA_CODEX_MVP_OK"}
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {"exact_match": 1 if ok else 0},
    }
