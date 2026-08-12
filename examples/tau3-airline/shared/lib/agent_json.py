"""Parse structured JSON from Agent invoke results."""

from __future__ import annotations

import json
import re
from typing import Any


def _loads_obj(blob: str) -> dict[str, Any] | None:
    """Parse a JSON object; allow raw control chars inside strings (LLM habit)."""
    try:
        # strict=False: models often emit real newlines inside "content" values.
        obj = json.loads(blob, strict=False)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


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
        obj = _loads_obj(m.group(1))
        if obj is not None:
            return obj
    # first brace object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return _loads_obj(text[start : end + 1])
    return None
