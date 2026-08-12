"""Core trajectory.jsonl writer — consumes ``bora.trajectory.event/1`` only.

Adapters map vendor-native streams into the neutral event contract. This module
folds those events into Viewer/Hub turn steps. Observational — never PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora.evidence.schema import EVENT_SCHEMA_VERSION

_TOOL_PHASES = frozenset({"start", "update"})


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
    """Write turn-level training trajectory for one BORA invoke.

    Consumes only events with ``schema == bora.trajectory.event/1``. Other
    rows are ignored (vendor raw belongs in ``backend_raw/`` / ``events.jsonl``).

    Row order: user → thought → tool_call/observation* → assistant →
    permission* → terminal.
    """
    inv_dir.mkdir(parents=True, exist_ok=True)
    path = inv_dir / "trajectory.jsonl"

    thought_parts: list[str] = []
    assistant_parts: list[str] = []
    permission_events: list[dict[str, Any]] = []
    tool_states: dict[str, dict[str, Any]] = {}
    session_id: str | None = None
    producer: str | None = None

    for ev in events:
        if not isinstance(ev, dict) or ev.get("schema") != EVENT_SCHEMA_VERSION:
            continue
        sid = ev.get("session_id")
        if isinstance(sid, str) and sid:
            session_id = sid
        src = ev.get("source")
        if isinstance(src, str) and src:
            producer = src
        kind = ev.get("kind")
        if kind == "text":
            text = ev.get("text") if isinstance(ev.get("text"), str) else ""
            channel = ev.get("channel")
            if channel == "thought" and text:
                thought_parts.append(text)
            elif channel == "assistant" and text:
                assistant_parts.append(text)
        elif kind == "tool":
            _merge_tool(tool_states, ev)
        elif kind == "permission":
            permission_events.append(
                {
                    "type": "permission_decision",
                    "outcome": ev.get("outcome"),
                    "option_id": ev.get("option_id"),
                    "policy": ev.get("policy"),
                    "source": producer or "bora",
                }
            )
        # kind == opaque: events.jsonl only

    merged_thought = "".join(thought_parts)
    merged_assistant = final_text if final_text else "".join(assistant_parts)

    turn_index = 1
    if isinstance(metadata, dict):
        raw_ti = metadata.get("turn_index")
        if isinstance(raw_ti, int) and raw_ti > 0:
            turn_index = raw_ti

    if producer is None and isinstance(metadata, dict):
        kind_meta = metadata.get("executor_kind") or metadata.get("plugin")
        if isinstance(kind_meta, str) and kind_meta:
            producer = kind_meta
    if producer is None:
        producer = "bora"

    lines: list[dict[str, Any]] = [
        {
            "type": "turn",
            "role": "user",
            "content": prompt,
            "turn_index": turn_index,
            "session_id": session_id,
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
                "session_id": session_id,
                "source": producer,
            }
        )

    for call_id, state in tool_states.items():
        _finalize_tool_state(state)
        tool_line: dict[str, Any] = {
            "type": "tool_call",
            "tool_call_id": call_id,
            "title": state.get("title"),
            "function_name": state.get("function_name") or "tool",
            "kind": state.get("tool_kind"),
            "status": state.get("status"),
            "turn_index": turn_index,
            "session_id": session_id,
            "source": producer,
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
                "session_id": session_id,
                "source": producer,
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
            "session_id": session_id,
            "source": producer,
        }
    )
    for pe in permission_events:
        pe = {**pe, "turn_index": turn_index, "session_id": session_id}
        lines.append(pe)

    meta_out: dict[str, Any] = {}
    if isinstance(metadata, dict):
        for k, v in metadata.items():
            meta_out[k] = v
    lines.append(
        {
            "type": "terminal",
            "ok": ok,
            "error": error,
            "turn_index": turn_index,
            "session_id": session_id,
            "structured": structured,
            "usage": usage,
            "stop_reason": (metadata or {}).get("stop_reason") if metadata else None,
            "metadata": meta_out,
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


def _merge_tool(tool_states: dict[str, dict[str, Any]], ev: dict[str, Any]) -> None:
    call_id = ev.get("tool_call_id")
    if not isinstance(call_id, str) or not call_id:
        return
    phase = ev.get("phase")
    if phase not in _TOOL_PHASES and phase is not None:
        return

    state = tool_states.setdefault(
        call_id,
        {
            "tool_call_id": call_id,
            "args": {},
            "observation_chunks": [],
        },
    )

    title = ev.get("title")
    if isinstance(title, str) and title:
        prev = state.get("title")
        if not isinstance(prev, str) or len(title) >= len(prev):
            state["title"] = title

    for key, dest in (
        ("function_name", "function_name"),
        ("tool_kind", "tool_kind"),
        ("status", "status"),
    ):
        val = ev.get(key)
        if val is not None:
            state[dest] = val if isinstance(val, str) else str(val)

    if ev.get("args") is not None:
        state["args"] = ev["args"] if isinstance(ev["args"], dict) else {"value": ev["args"]}
        state["args_from_event"] = True

    if ev.get("raw_output") is not None:
        state["raw_output"] = ev["raw_output"]

    content = ev.get("content")
    if isinstance(content, str) and content:
        chunks: list[str] = state.setdefault("observation_chunks", [])
        if not chunks or chunks[-1] != content:
            chunks.append(content)


def _finalize_tool_state(state: dict[str, Any]) -> None:
    if not state.get("function_name") or state.get("function_name") == "tool":
        kind = state.get("tool_kind")
        if isinstance(kind, str) and kind and kind != "other":
            state["function_name"] = kind
        else:
            title = state.get("title")
            if isinstance(title, str) and title.strip():
                state["function_name"] = title.strip().splitlines()[0]
            else:
                state["function_name"] = "tool"

    chunks: list[str] = list(state.get("observation_chunks") or [])
    if chunks:
        state["content"] = "\n\n".join(chunks)
    if state.get("args") is None:
        state["args"] = {}


def _should_emit_observation(state: dict[str, Any]) -> bool:
    if state.get("content"):
        return True
    if state.get("raw_output") is not None:
        return True
    status = state.get("status")
    return isinstance(status, str) and status.lower() in {"completed", "failed"}
