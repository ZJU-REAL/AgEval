"""Map ACP session/update events to ``bora.trajectory.event/1``.

Does not write ``trajectory.jsonl``. Harbor-aligned tool fold lives in the
Core writer after this mapping.
"""

from __future__ import annotations

import json
from typing import Any

from bora.evidence.schema import EVENT_SCHEMA_VERSION

_SOURCE = "acp"


def acp_session_events_to_bora(
    events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Translate ACP client events into the Core-owned trajectory contract."""
    out: list[dict[str, Any]] = []
    seq = 0
    longest_title: dict[str, str] = {}
    had_raw_input: set[str] = set()
    tool_kind_by_id: dict[str, str] = {}

    for raw in events:
        if not isinstance(raw, dict):
            continue
        sid = raw.get("session_id") if isinstance(raw.get("session_id"), str) else None

        if raw.get("type") == "permission_decision":
            seq += 1
            out.append(
                {
                    "schema": EVENT_SCHEMA_VERSION,
                    "seq": seq,
                    "session_id": sid,
                    "source": _SOURCE,
                    "kind": "permission",
                    "outcome": raw.get("outcome"),
                    "option_id": raw.get("option_id"),
                    "policy": raw.get("policy"),
                }
            )
            continue

        if raw.get("channel") in {"thought", "assistant"} and isinstance(raw.get("text"), str):
            seq += 1
            out.append(
                {
                    "schema": EVENT_SCHEMA_VERSION,
                    "seq": seq,
                    "session_id": sid,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": raw["channel"],
                    "text": raw["text"],
                }
            )
            # A session_update may also carry a tool payload; fall through.

        upd = raw.get("update") if isinstance(raw.get("update"), dict) else {}
        su = _session_update_name(raw, upd)
        if su not in {"tool_call", "tool_call_update"}:
            continue

        call_id = _tool_call_id(raw, upd)
        if not call_id:
            continue

        title = upd.get("title") if isinstance(upd.get("title"), str) else raw.get("title")
        kind = upd.get("kind") if upd.get("kind") is not None else raw.get("kind")
        status = upd.get("status") if upd.get("status") is not None else raw.get("status")
        raw_input = upd.get("rawInput") if "rawInput" in upd else upd.get("raw_input")
        raw_output = upd.get("rawOutput") if "rawOutput" in upd else upd.get("raw_output")
        content_text = _stringify_tool_output(raw_output, upd.get("content"))
        term = _terminal_meta_text(upd)
        if term:
            content_text = term if not content_text else f"{content_text}\n\n{term}"

        args: dict[str, Any] | None = None
        if raw_input is not None:
            args = raw_input if isinstance(raw_input, dict) else {"value": raw_input}
            had_raw_input.add(call_id)
        if isinstance(title, str) and title.strip():
            prev_t = longest_title.get(call_id)
            if prev_t is None or len(title) >= len(prev_t):
                longest_title[call_id] = title
        if isinstance(kind, str) and kind:
            tool_kind_by_id[call_id] = kind

        function_name = _resolve_tool_name(
            {
                "kind": kind if isinstance(kind, str) else None,
                "title": title if isinstance(title, str) else None,
            }
        )

        seq += 1
        ev: dict[str, Any] = {
            "schema": EVENT_SCHEMA_VERSION,
            "seq": seq,
            "session_id": sid,
            "source": _SOURCE,
            "kind": "tool",
            "phase": "start" if su == "tool_call" else "update",
            "tool_call_id": call_id,
            "title": title if isinstance(title, str) else None,
            "function_name": function_name,
            "tool_kind": kind
            if isinstance(kind, str)
            else (str(kind) if kind is not None else None),
            "status": (
                status if isinstance(status, str) else (str(status) if status is not None else None)
            ),
            "args": args,
            "content": content_text,
            "raw_output": raw_output,
        }
        out.append(ev)

    for call_id, title in longest_title.items():
        if call_id in had_raw_input:
            continue
        kind_l = (tool_kind_by_id.get(call_id) or "").lower()
        if kind_l not in {"execute", "other", ""}:
            continue
        seq += 1
        out.append(
            {
                "schema": EVENT_SCHEMA_VERSION,
                "seq": seq,
                "session_id": out[-1].get("session_id") if out else None,
                "source": _SOURCE,
                "kind": "tool",
                "phase": "update",
                "tool_call_id": call_id,
                "title": title,
                "args": {"command": title},
            }
        )
    return out


def _session_update_name(ev: dict[str, Any], upd: dict[str, Any]) -> str:
    su = upd.get("sessionUpdate") or upd.get("session_update")
    if isinstance(su, str) and su:
        return su.lower().replace("-", "_")
    ut = ev.get("update_type")
    if isinstance(ut, str) and ut:
        compact = ut.lower().replace("_", "")
        if "toolcallprogress" in compact or "toolcallupdate" in compact:
            return "tool_call_update"
        if "toolcallstart" in compact or (
            "toolcall" in compact and "update" not in compact and "progress" not in compact
        ):
            return "tool_call"
    return ""


def _tool_call_id(ev: dict[str, Any], upd: dict[str, Any]) -> str | None:
    for src in (upd, ev):
        for key in ("toolCallId", "tool_call_id"):
            val = src.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _resolve_tool_name(update: dict[str, Any]) -> str:
    kind = update.get("kind")
    if isinstance(kind, str) and kind and kind != "other":
        return kind
    title = update.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip().splitlines()[0]
    return "tool"


def _extract_text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_extract_text_from_content(item) for item in content)
    if isinstance(content, dict):
        if content.get("type") == "terminal":
            return ""
        text = content.get("text")
        if isinstance(text, str):
            return text
        nested = content.get("content")
        if nested is not None:
            return _extract_text_from_content(nested)
        if content.get("type") == "diff" or "newText" in content or "new_text" in content:
            path = content.get("path") or ""
            new = content.get("newText") if "newText" in content else content.get("new_text")
            if isinstance(new, str):
                return f"[diff {path}]\n{new}"
            return f"[diff {path}]".strip() if path else ""
    return ""


def _stringify_tool_output(raw_output: Any, content: Any) -> str | None:
    if isinstance(raw_output, dict):
        for key in ("output", "formatted_output", "aggregated_output"):
            value = raw_output.get(key)
            if isinstance(value, str) and value:
                return value
        if any(key in raw_output for key in ("stdout", "stderr", "exit_code", "status")):
            return json.dumps(raw_output, ensure_ascii=False, sort_keys=True)
    elif raw_output is not None:
        return str(raw_output)
    text = _extract_text_from_content(content)
    return text or None


def _terminal_meta_text(upd: dict[str, Any]) -> str | None:
    meta = upd.get("_meta") if isinstance(upd.get("_meta"), dict) else None
    if meta is None:
        meta = upd.get("field_meta") if isinstance(upd.get("field_meta"), dict) else None
    if meta is None:
        return None
    term = meta.get("terminal_output")
    if isinstance(term, dict):
        data = term.get("data")
        if isinstance(data, str) and data:
            return data
    return None
