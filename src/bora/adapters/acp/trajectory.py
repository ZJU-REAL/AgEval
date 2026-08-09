"""Write ACP trajectory.jsonl evidence (observational)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_trajectory_jsonl(
    inv_dir: Path,
    *,
    prompt: str,
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    final_text: str,
    structured: dict[str, object] | None,
    usage: dict[str, Any] | None,
    ok: bool,
    error: str | None,
    metadata: dict[str, Any] | None = None,
    redaction_sentinels: tuple[str, ...] | list[str] | None = None,
) -> Path:
    """Write **turn-level** training trajectory for one BORA invoke.

    One ``session/prompt`` (one invoke) → one training turn unit:

    1. ``user`` — full prompt
    2. ``assistant`` (optional ``part=thought``) — merged thought text
    3. ``tool_call`` / ``observation`` pairs — merged from ACP stream
    4. ``assistant`` — merged message text (prefer ``final_text``)
    5. ``permission_decision`` — batch auto-approve evidence (if any)
    6. ``terminal`` — ok / error / structured / usage / stop metadata

    Stream chunks are merged; raw token-level ACP updates are not written here.
    Optional debug stream stays out of this file (see ``events.jsonl`` if needed).
    Not PASS authority.
    """
    inv_dir.mkdir(parents=True, exist_ok=True)
    path = inv_dir / "trajectory.jsonl"

    thought_parts: list[str] = []
    assistant_parts: list[str] = []
    permission_events: list[dict[str, Any]] = []
    acp_session_id: str | None = None
    # toolCallId → merged state; insertion order = first appearance
    tool_states: dict[str, dict[str, Any]] = {}

    for ev in events:
        if not isinstance(ev, dict):
            continue
        sid = ev.get("session_id")
        if isinstance(sid, str) and sid:
            acp_session_id = sid
        if ev.get("type") == "permission_decision":
            permission_events.append(
                {
                    "type": "permission_decision",
                    "outcome": ev.get("outcome"),
                    "option_id": ev.get("option_id"),
                    "policy": ev.get("policy"),
                    "source": "acp",
                }
            )
            continue

        _merge_tool_from_event(ev, tool_states)

        channel = ev.get("channel")
        text = ev.get("text")
        if not isinstance(text, str):
            continue
        if channel == "thought":
            thought_parts.append(text)
        elif channel == "assistant":
            assistant_parts.append(text)

    merged_thought = "".join(thought_parts)
    merged_assistant = final_text if final_text else "".join(assistant_parts)

    turn_index = 1
    if isinstance(metadata, dict):
        # Optional: callers may pass bora turn index later.
        raw_ti = metadata.get("turn_index")
        if isinstance(raw_ti, int) and raw_ti > 0:
            turn_index = raw_ti

    lines: list[dict[str, Any]] = [
        {
            "type": "turn",
            "role": "user",
            "content": prompt,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "bora",
        }
    ]
    if merged_thought:
        lines.append(
            {
                "type": "turn",
                "role": "assistant",
                "part": "thought",
                "content": merged_thought,
                "turn_index": turn_index,
                "acp_session_id": acp_session_id,
                "source": "acp",
            }
        )

    for call_id, state in tool_states.items():
        tool_line: dict[str, Any] = {
            "type": "tool_call",
            "tool_call_id": call_id,
            "title": state.get("title"),
            "function_name": state.get("function_name"),
            "kind": state.get("kind"),
            "status": state.get("status"),
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "acp",
        }
        if state.get("args") is not None:
            tool_line["args"] = state["args"]
        # Drop null-only optional display fields for cleaner JSONL.
        lines.append(
            {
                k: v
                for k, v in tool_line.items()
                if v is not None or k in {"type", "tool_call_id", "turn_index", "source"}
            }
        )

        if _should_emit_observation(state):
            obs: dict[str, Any] = {
                "type": "observation",
                "tool_call_id": call_id,
                "status": state.get("status"),
                "turn_index": turn_index,
                "acp_session_id": acp_session_id,
                "source": "acp",
            }
            if state.get("content") is not None:
                obs["content"] = state["content"]
            if state.get("raw_output") is not None:
                obs["raw_output"] = state["raw_output"]
            lines.append(
                {
                    k: v
                    for k, v in obs.items()
                    if v is not None or k in {"type", "tool_call_id", "turn_index", "source"}
                }
            )

    lines.append(
        {
            "type": "turn",
            "role": "assistant",
            "content": merged_assistant,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "acp",
        }
    )
    for pe in permission_events:
        pe = {**pe, "turn_index": turn_index, "acp_session_id": acp_session_id}
        lines.append(pe)
    lines.append(
        {
            "type": "terminal",
            "ok": ok,
            "error": error,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "structured": structured,
            "usage": usage,
            "stop_reason": (metadata or {}).get("stop_reason") if metadata else None,
            "metadata": {
                k: (metadata or {}).get(k)
                for k in (
                    "executor_kind",
                    "acp_entry_id",
                    "acp_version",
                    "protocol_version",
                    "actual_model",
                    "locked_model",
                )
                if metadata and k in metadata
            },
            "source": "bora",
        }
    )

    sentinels = tuple(s for s in (redaction_sentinels or ()) if s)
    if sentinels:
        from bora.evidence.redaction import redact_value

        lines = [redact_value(line, extra_sentinels=sentinels) for line in lines]
    else:
        # Still scrub common secret shapes even without explicit sentinels.
        from bora.evidence.redaction import redact_value

        lines = [redact_value(line) for line in lines]

    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _session_update_name(ev: dict[str, Any]) -> str:
    """Return normalized ACP sessionUpdate name, or empty string."""
    upd = ev.get("update")
    if isinstance(upd, dict):
        su = upd.get("sessionUpdate") or upd.get("session_update")
        if isinstance(su, str) and su:
            return su.lower().replace("-", "_")
    # Fallback: typed class name from client
    ut = ev.get("update_type")
    if isinstance(ut, str) and ut:
        low = ut.lower()
        if "toolcallupdate" in low.replace("_", "") or "tool_call_update" in low:
            return "tool_call_update"
        # ToolCall / SessionUpdateToolCall — not update
        if "toolcall" in low.replace("_", "") and "update" not in low:
            return "tool_call"
        if low in {"tool_call", "toolcall"}:
            return "tool_call"
        if low in {"tool_call_update", "toolcallupdate"}:
            return "tool_call_update"
    # Flat helpers imply a tool-related event when tool_call_id is present
    if ev.get("tool_call_id") or (
        isinstance(upd, dict) and (upd.get("toolCallId") or upd.get("tool_call_id"))
    ):
        # Prefer update when status-only progress is likely, but without name
        # treat as tool_call seed (merge is idempotent).
        return "tool_call"
    return ""


def _tool_call_id_from_event(ev: dict[str, Any]) -> str | None:
    tid = ev.get("tool_call_id")
    if isinstance(tid, str) and tid:
        return tid
    upd = ev.get("update")
    if isinstance(upd, dict):
        for key in ("toolCallId", "tool_call_id"):
            val = upd.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _merge_tool_from_event(ev: dict[str, Any], tool_states: dict[str, dict[str, Any]]) -> None:
    name = _session_update_name(ev)
    call_id = _tool_call_id_from_event(ev)
    if not call_id:
        return
    # Require an explicit tool sessionUpdate name, or flat tool_call_id on a
    # session_update event (client already stamped helpers).
    if name not in {"tool_call", "tool_call_update"} and ev.get("type") != "session_update":
        return

    upd = ev.get("update") if isinstance(ev.get("update"), dict) else {}
    state = tool_states.setdefault(call_id, {"tool_call_id": call_id})

    # Prefer nested update fields; fall back to flat client helpers.
    title = upd.get("title") if isinstance(upd.get("title"), str) else ev.get("title")
    if isinstance(title, str) and title:
        state["title"] = title

    kind = upd.get("kind") if upd.get("kind") is not None else ev.get("kind")
    if kind is not None:
        state["kind"] = kind if isinstance(kind, str) else str(kind)

    status = upd.get("status") if upd.get("status") is not None else ev.get("status")
    if status is not None:
        state["status"] = status if isinstance(status, str) else str(status)

    raw_input = upd.get("rawInput") if "rawInput" in upd else upd.get("raw_input")
    if raw_input is not None:
        state["args"] = raw_input

    raw_output = upd.get("rawOutput") if "rawOutput" in upd else upd.get("raw_output")
    if raw_output is not None:
        state["raw_output"] = raw_output

    content = upd.get("content")
    if content is not None:
        summarized = _summarize_tool_content(content)
        if summarized:
            state["content"] = summarized

    # Best-effort function_name
    if "function_name" not in state:
        state["function_name"] = _infer_function_name(state)


def _infer_function_name(state: dict[str, Any]) -> str | None:
    args = state.get("args")
    if isinstance(args, dict):
        for key in ("name", "tool", "toolName", "tool_name", "command", "function"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    title = state.get("title")
    if isinstance(title, str) and title.strip():
        # Use first token / short title as display name
        return title.strip()[:120]
    kind = state.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    return None


def _summarize_tool_content(content: Any) -> str | None:
    """Collapse ACP ToolCallContent[] (or string) into a readable observation string."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        item_type = item.get("type")
        if item_type == "content" or "content" in item:
            inner = item.get("content")
            if isinstance(inner, dict):
                text = inner.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    try:
                        parts.append(json.dumps(inner, ensure_ascii=False))
                    except (TypeError, ValueError):
                        parts.append(str(inner))
            elif isinstance(inner, str):
                parts.append(inner)
        elif item_type == "diff":
            path = item.get("path") or ""
            parts.append(f"[diff {path}]".strip())
        elif item_type == "terminal":
            tid = item.get("terminalId") or item.get("terminal_id") or ""
            parts.append(f"[terminal {tid}]".strip())
        else:
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
            else:
                try:
                    parts.append(json.dumps(item, ensure_ascii=False))
                except (TypeError, ValueError):
                    parts.append(str(item))
    joined = "\n".join(p for p in parts if p)
    return joined or None


def _should_emit_observation(state: dict[str, Any]) -> bool:
    if state.get("content") is not None:
        return True
    if state.get("raw_output") is not None:
        return True
    status = state.get("status")
    return isinstance(status, str) and status.lower() in {"completed", "failed"}
