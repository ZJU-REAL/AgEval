"""Map NVIDIA nooa event_manager dumps to ``bora.trajectory.event/1``.

Vendor-native rows stay in ``backend_raw/``. This module never emits ACP
``session_update`` shapes.
"""

from __future__ import annotations

import json
from typing import Any

SCHEMA = "bora.trajectory.event/1"
_SOURCE = "nooa"
_OPAQUE_CLIP = 8_000


def dump_native_events(agent: Any) -> list[dict[str, Any]]:
    """Snapshot ``agent.event_manager`` as JSON-friendly dicts."""
    em = getattr(agent, "event_manager", None)
    if em is None:
        return []
    items = getattr(em, "items", None)
    if not callable(items):
        return []
    out: list[dict[str, Any]] = []
    try:
        pairs = items()
    except Exception:  # noqa: BLE001
        return []
    for tag, ev in pairs:
        row = _event_to_dict(ev)
        if row is None:
            continue
        if tag is not None:
            row.setdefault("tag", str(tag))
        out.append(row)
    return out


def to_bora_trajectory_events(
    raw_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    session_id: str = "nooa",
) -> list[dict[str, Any]]:
    """Native nooa dump → Core-owned trajectory events."""
    out: list[dict[str, Any]] = []
    seq = 0
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        et = _event_type(raw)
        if et == "Task":
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": "thought",
                    "text": str(raw.get("prompt") or ""),
                }
            )
        elif et in {"Message", "LLMOutput", "TextOnlyReply"}:
            text = raw.get("content")
            if not isinstance(text, str):
                text = str(text or "")
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": "assistant",
                    "text": text,
                }
            )
        elif et == "Reasoning":
            text = raw.get("content")
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": "thought",
                    "text": str(text or ""),
                }
            )
        elif et in {"ToolCallEvent", "ToolCall"}:
            seq += 1
            call_id = str(raw.get("tool_call_id") or raw.get("id") or f"nooa_tool_{seq}")
            name = str(raw.get("name") or raw.get("tool") or "tool")
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "tool",
                    "phase": "start",
                    "tool_call_id": call_id,
                    "title": name,
                    "function_name": name,
                    "tool_kind": _tool_kind(name),
                    "status": "pending",
                    "args": raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {},
                }
            )
            if raw.get("result") is not None:
                seq += 1
                result = raw["result"]
                out.append(
                    {
                        "schema": SCHEMA,
                        "seq": seq,
                        "session_id": session_id,
                        "source": _SOURCE,
                        "kind": "tool",
                        "phase": "update",
                        "tool_call_id": call_id,
                        "title": name,
                        "function_name": name,
                        "tool_kind": _tool_kind(name),
                        "status": "failed" if _is_error_result(result) else "completed",
                        "content": _stringify_result(result),
                        "raw_output": result,
                    }
                )
        elif et == "PythonOutput":
            seq += 1
            call_id = str(raw.get("tool_call_id") or f"nooa_py_{seq}")
            payload = {
                k: raw.get(k)
                for k in (
                    "execution_status",
                    "stdout",
                    "stderr",
                    "error",
                    "value",
                    "explicit_return",
                )
            }
            status = (
                "completed"
                if str(payload.get("execution_status") or "").lower()
                in {"", "none", "complete", "completed"}
                else "failed"
            )
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "tool",
                    "phase": "start",
                    "tool_call_id": call_id,
                    "title": "execute_python",
                    "function_name": "execute_python",
                    "tool_kind": "execute",
                    "status": "pending",
                    "args": {},
                }
            )
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "tool",
                    "phase": "update",
                    "tool_call_id": call_id,
                    "title": "execute_python",
                    "function_name": "execute_python",
                    "tool_kind": "execute",
                    "status": status,
                    "content": _python_obs_text(payload),
                    "raw_output": payload,
                }
            )
        else:
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "opaque",
                    "payload": _clip(raw),
                }
            )
    return out


def _event_type(raw: dict[str, Any]) -> str:
    for key in ("event_type", "type", "kind"):
        val = raw.get(key)
        if isinstance(val, str) and val:
            return val.rsplit(".", 1)[-1]
    return ""


def _event_to_dict(ev: Any) -> dict[str, Any] | None:
    if isinstance(ev, dict):
        row = dict(ev)
    elif hasattr(ev, "model_dump") and callable(ev.model_dump):
        try:
            dumped = ev.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            try:
                dumped = ev.model_dump()
            except Exception:  # noqa: BLE001
                dumped = None
        row = dumped if isinstance(dumped, dict) else None
    else:
        row = None
    if row is None:
        return None
    name = type(ev).__name__ if not isinstance(ev, dict) else _event_type(row)
    if name and "event_type" not in row:
        row["event_type"] = name
    return row


def _tool_kind(name: str) -> str:
    lowered = name.lower()
    if "python" in lowered or "exec" in lowered or "bash" in lowered or "shell" in lowered:
        return "execute"
    if "read" in lowered or "cat" in lowered:
        return "read"
    if "write" in lowered or "edit" in lowered:
        return "edit"
    return "other"


def _is_error_result(result: Any) -> bool:
    if isinstance(result, dict):
        status = str(result.get("status") or result.get("execution_status") or "").lower()
        if status in {"error", "failed", "fail"}:
            return True
        if result.get("error"):
            return True
    return False


def _stringify_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


def _python_obs_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    error = payload.get("error")
    value = payload.get("value")
    if isinstance(stdout, str) and stdout:
        parts.append(stdout)
    if isinstance(stderr, str) and stderr:
        parts.append(stderr)
    if error:
        parts.append(str(error))
    if value is not None and not parts:
        parts.append(_stringify_result(value))
    return "\n".join(parts)


def _clip(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        blob = json.dumps(raw, ensure_ascii=False, default=str)
    except TypeError:
        return {"repr": str(raw)[:_OPAQUE_CLIP]}
    if len(blob) <= _OPAQUE_CLIP:
        return raw
    return {"clipped": True, "preview": blob[:_OPAQUE_CLIP]}
