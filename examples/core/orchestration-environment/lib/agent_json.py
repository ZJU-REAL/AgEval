"""Parse agent invoke results into JSON objects."""

from __future__ import annotations

import json
from typing import Any


def parse_json_obj(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.rfind("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def agent_struct(resp: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(resp.get("structured"), dict):
        return resp["structured"]  # type: ignore[return-value]
    return parse_json_obj(str(resp.get("text") or ""))
