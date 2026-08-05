"""Minimal evaluator for registry fixture."""

from __future__ import annotations

from typing import Any


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    raw = inputs.get("result")
    ok = isinstance(raw, dict) and raw.get("ok") is True
    return {"status": "PASS" if ok else "FAIL", "score": 1.0 if ok else 0.0}
