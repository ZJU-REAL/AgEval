"""Parse structured JSON from Agent invoke results."""

from __future__ import annotations

import json
import re
from typing import Any


def agent_struct(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    structured = result.get("structured")
    if isinstance(structured, dict):
        return structured
    text = result.get("text") or result.get("content") or ""
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    # fenced json
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    # first brace object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
