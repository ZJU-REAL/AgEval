"""Write ACP trajectory.jsonl evidence (observational).

Tool synthesis follows the same *role* as Harbor ATIF export from ACP events:
fold ``session/update`` tool streams into structured steps. Not PASS authority.

**L0 (protocol, Harbor-aligned):** ``sessionUpdate`` in
``{tool_call, tool_call_update}``, key by ``toolCallId``, name from ``kind`` /
``title``, args from ``rawInput``, observation from ``rawOutput`` + text-bearing
``content``.

**L1 (explicit extensions, documented):**

- ``update._meta.terminal_output.data`` → observation text (pi-style vendor meta)
- when ``args`` still empty and ``kind==execute`` with a final ``title``,
  ``args={"command": title}`` (title stream, not inventing tools)
"""

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

    Not PASS authority. Raw token stream stays in ``events.jsonl`` if needed.
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
        _finalize_tool_state(state)
        tool_line: dict[str, Any] = {
            "type": "tool_call",
            "tool_call_id": call_id,
            "title": state.get("title"),
            "function_name": state.get("function_name") or "tool",
            "kind": state.get("kind"),
            "status": state.get("status"),
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "acp",
        }
        args = state.get("args")
        if args is not None:
            tool_line["args"] = args
        lines.append(_drop_nulls(tool_line, keep={"type", "tool_call_id", "turn_index", "source"}))

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
            lines.append(_drop_nulls(obs, keep={"type", "tool_call_id", "turn_index", "source"}))

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

    from bora.evidence.redaction import redact_value

    sentinels = tuple(s for s in (redaction_sentinels or ()) if s)
    lines = [redact_value(line, extra_sentinels=sentinels) for line in lines]

    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _drop_nulls(row: dict[str, Any], *, keep: set[str]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None or k in keep}


def _update_payload(ev: dict[str, Any]) -> dict[str, Any]:
    """Nested ACP update dict (preferred) or empty."""
    raw = ev.get("update")
    return raw if isinstance(raw, dict) else {}


def _session_update_name(ev: dict[str, Any], upd: dict[str, Any]) -> str:
    """Normalized sessionUpdate name (Harbor: only tool_call / tool_call_update)."""
    su = upd.get("sessionUpdate") or upd.get("session_update")
    if isinstance(su, str) and su:
        return su.lower().replace("-", "_")
    # Typed dump fallback (client update_type)
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


def _merge_tool_from_event(ev: dict[str, Any], tool_states: dict[str, dict[str, Any]]) -> None:
    """L0 Harbor-style fold + L1 meta/title extensions."""
    upd = _update_payload(ev)
    name = _session_update_name(ev, upd)
    if name not in {"tool_call", "tool_call_update"}:
        return

    call_id = _tool_call_id(ev, upd)
    if not call_id:
        return

    state = tool_states.setdefault(
        call_id,
        {
            "tool_call_id": call_id,
            "args": {},  # Harbor default until rawInput arrives
            "observation_chunks": [],
        },
    )

    # --- L0 protocol fields (prefer nested update, fall back to flat client helpers) ---
    title = upd.get("title") if isinstance(upd.get("title"), str) else ev.get("title")
    if isinstance(title, str) and title:
        # Title may stream; keep the longest form (final command / label).
        prev = state.get("title")
        if not isinstance(prev, str) or len(title) >= len(prev):
            state["title"] = title

    kind = upd.get("kind") if upd.get("kind") is not None else ev.get("kind")
    if kind is not None:
        state["kind"] = kind if isinstance(kind, str) else str(kind)

    status = upd.get("status") if upd.get("status") is not None else ev.get("status")
    if status is not None:
        state["status"] = status if isinstance(status, str) else str(status)

    raw_input = upd.get("rawInput") if "rawInput" in upd else upd.get("raw_input")
    if raw_input is not None:
        state["args"] = _normalize_tool_arguments(raw_input)
        state["args_from_raw_input"] = True

    raw_output = upd.get("rawOutput") if "rawOutput" in upd else upd.get("raw_output")
    if raw_output is not None:
        state["raw_output"] = raw_output

    # Harbor: observation from rawOutput and/or text-bearing content
    obs = _stringify_tool_output(raw_output, upd.get("content"))
    if obs:
        chunks: list[str] = state.setdefault("observation_chunks", [])
        if not chunks or chunks[-1] != obs:
            chunks.append(obs)

    # --- L1: vendor meta terminal stdout (pi) ---
    _merge_terminal_meta(upd, state)

    # function_name: Harbor _resolve_tool_name (kind else title first line)
    if not state.get("function_name") or state.get("function_name") == "tool":
        state["function_name"] = _resolve_tool_name(upd if upd else state)


def _normalize_tool_arguments(raw_input: Any) -> dict[str, Any]:
    """Harbor-compatible args object."""
    if isinstance(raw_input, dict):
        return raw_input
    if raw_input is None:
        return {}
    return {"value": raw_input}


def _resolve_tool_name(update: dict[str, Any]) -> str:
    """Harbor: kind (if not other) else title first line else 'tool'."""
    kind = update.get("kind")
    if isinstance(kind, str) and kind and kind != "other":
        return kind
    title = update.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip().splitlines()[0]
    return "tool"


def _extract_text_from_content(content: Any) -> str:
    """Harbor-style: walk content tree for text; ignore pure terminal id blocks."""
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
        # diff: surface path + newText when present
        if content.get("type") == "diff" or "newText" in content or "new_text" in content:
            path = content.get("path") or ""
            new = content.get("newText") if "newText" in content else content.get("new_text")
            if isinstance(new, str):
                return f"[diff {path}]\n{new}"
            return f"[diff {path}]".strip() if path else ""
    return ""


def _stringify_tool_output(raw_output: Any, content: Any) -> str | None:
    """Harbor _stringify_tool_output."""
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


def _merge_terminal_meta(upd: dict[str, Any], state: dict[str, Any]) -> None:
    """L1: ``_meta.terminal_output.data`` (and terminal_exit) when present."""
    meta = upd.get("_meta") if isinstance(upd.get("_meta"), dict) else None
    if meta is None:
        # alias used by some dumps
        meta = upd.get("field_meta") if isinstance(upd.get("field_meta"), dict) else None
    if meta is None:
        return

    term = meta.get("terminal_output")
    if isinstance(term, dict):
        data = term.get("data")
        if isinstance(data, str) and data:
            prev = state.get("terminal_output")
            if (
                not isinstance(prev, str)
                or not prev
                or data.startswith(prev)
                or len(data) >= len(prev)
            ):
                state["terminal_output"] = data
            elif not prev.endswith(data):
                state["terminal_output"] = prev + data

    exit_info = meta.get("terminal_exit")
    if exit_info is not None:
        state["terminal_exit"] = exit_info


def _finalize_tool_state(state: dict[str, Any]) -> None:
    """Collapse chunks; apply L1 title→command when rawInput never arrived."""
    # function_name from final kind/title (Harbor)
    state["function_name"] = _resolve_tool_name(
        {
            "kind": state.get("kind"),
            "title": state.get("title"),
        }
    )

    # L1: execute tools often stream command into title without rawInput
    if not state.get("args_from_raw_input"):
        title = state.get("title")
        kind = state.get("kind")
        kind_l = kind.lower() if isinstance(kind, str) else ""
        if (
            isinstance(title, str)
            and title.strip()
            and kind_l in {"execute", "other", ""}
            and (not state.get("args") or state.get("args") == {})
        ):
            state["args"] = {"command": title}

    # Observation content: protocol chunks + L1 terminal meta
    chunks: list[str] = list(state.get("observation_chunks") or [])
    term_out = state.get("terminal_output")
    if isinstance(term_out, str) and term_out:
        if not chunks or all(c.startswith("[terminal ") for c in chunks):
            chunks = [term_out]
        elif term_out not in "\n\n".join(chunks):
            chunks.append(term_out)

    if chunks:
        state["content"] = "\n\n".join(chunks)

    if state.get("args") is None:
        state["args"] = {}


def _should_emit_observation(state: dict[str, Any]) -> bool:
    if state.get("content"):
        return True
    if state.get("raw_output") is not None:
        return True
    # Harbor skips empty observation; we still emit on terminal status when
    # completed/failed so the action chain is visible (status-only).
    status = state.get("status")
    return isinstance(status, str) and status.lower() in {"completed", "failed"}
