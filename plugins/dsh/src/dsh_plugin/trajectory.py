"""Map DeepSeek Harness session events to ``bora.trajectory.event/1``.

Vendor-native rows stay in ``backend_raw/``. This module never emits ACP
``session_update`` shapes. Importable in-image (no BORA Core).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

SCHEMA = "bora.trajectory.event/1"
_SOURCE = "dsh"
_OPAQUE_CLIP = 8_000

# Streaming / bookkeeping — dump as vendor raw, do not fold token deltas.
_SKIP_TYPES = frozenset(
    {
        "assistant/chunk",
        "reasoning-chunks",
        "text-chunks",
        "tool-call-chunks",
        "request/header",
        "request/context",
        "session/title",
        "session",
        "agent/inbox/spliced",
        "turn/start",
        "step/start",
        "step/end",
        "user/message",
    }
)


def to_bora_trajectory_events(
    raw_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    session_id: str = "dsh",
) -> list[dict[str, Any]]:
    """Committed DSH session events → Core-owned trajectory events."""
    out: list[dict[str, Any]] = []
    seq = 0
    names: dict[str, str] = {}
    started_at: dict[str, str] = {}

    def _next() -> int:
        nonlocal seq
        seq += 1
        return seq

    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        event = _unwrap_event(raw)
        et = str(event.get("type") or "")
        if et in _SKIP_TYPES:
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if et == "assistant/message":
            seq = _emit_assistant_message(out, _next, session_id, data)
        elif et == "tool/call":
            seq_n = _next()
            call_id = str(data.get("callId") or data.get("id") or f"dsh_tool_{seq_n}")
            name = str(data.get("name") or "tool")
            names[call_id] = name
            start = {
                "schema": SCHEMA,
                "seq": seq_n,
                "session_id": session_id,
                "source": _SOURCE,
                "kind": "tool",
                "phase": "start",
                "tool_call_id": call_id,
                "title": name,
                "function_name": name,
                "tool_kind": _tool_kind(name),
                "status": "pending",
                "args": _as_args(data.get("arguments")),
            }
            _attach_timing(start, event, data, raw)
            if isinstance(start.get("at"), str):
                started_at[call_id] = start["at"]
                start.setdefault("started_at", start["at"])
            out.append(start)
        elif et == "tool/result":
            seq_n = _next()
            call_id, content, is_error = _parse_tool_result(data)
            name = names.get(call_id, "tool")
            update = {
                "schema": SCHEMA,
                "seq": seq_n,
                "session_id": session_id,
                "source": _SOURCE,
                "kind": "tool",
                "phase": "update",
                "tool_call_id": call_id or f"dsh_tool_{seq_n}",
                "title": name,
                "function_name": name,
                "tool_kind": "other",
                "status": "failed" if is_error else "completed",
                "content": content,
            }
            _attach_timing(update, event, data, raw)
            call_key = str(update.get("tool_call_id") or "")
            start_iso = started_at.get(call_key)
            if start_iso:
                update.setdefault("started_at", start_iso)
            end_iso = update.get("at") if isinstance(update.get("at"), str) else None
            if end_iso:
                update.setdefault("ended_at", end_iso)
            if update.get("elapsed_ms") is None and start_iso and end_iso:
                elapsed = _iso_delta_ms(start_iso, end_iso)
                if elapsed is not None:
                    update["elapsed_ms"] = elapsed
            out.append(update)
        elif et == "turn/end":
            continue
        else:
            seq_n = _next()
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq_n,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "opaque",
                    "payload": _clip(event),
                }
            )
    return out


def extract_usage(
    raw_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    """Sum per-step committed usage for one Session.run interval.

    DSH emits usage on every ``assistant/message`` (and a matching
    ``assistant/chunk``). Last-step numbers are the current request only
    (cache grows, uncached input shrinks). Chunks are ignored so a
    message+chunk pair is not double-counted. Not ACP UsageUpdate.
    """
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "reasoning_tokens": 0,
    }
    seen = False
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        event = _unwrap_event(raw)
        if event.get("type") != "assistant/message":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        usage = data.get("usage")
        if not isinstance(usage, dict):
            continue
        part = _normalize_usage(usage)
        if not part:
            continue
        seen = True
        for key in totals:
            val = part.get(key)
            if isinstance(val, int):
                totals[key] += val
    if not seen:
        return None
    out = {k: v for k, v in totals.items() if v or k in {"input_tokens", "output_tokens"}}
    out["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return out


def extract_finish_reason(
    raw_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> str | None:
    for raw in reversed(list(raw_events)):
        if not isinstance(raw, dict):
            continue
        event = _unwrap_event(raw)
        if event.get("type") != "turn/end":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        reason = data.get("reason") if isinstance(data.get("reason"), dict) else {}
        kind = reason.get("kind")
        if isinstance(kind, str) and kind:
            return kind
    return None


def _emit_assistant_message(
    out: list[dict[str, Any]],
    next_seq: Any,
    session_id: str,
    data: dict[str, Any],
) -> int:
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return 0
    seq = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "")
        if btype == "reasoning":
            text = str(block.get("text") or "")
            if text:
                seq = next_seq()
                out.append(_text(seq, session_id, "thought", text))
        elif btype == "text":
            text = str(block.get("text") or "")
            if text:
                seq = next_seq()
                out.append(_text(seq, session_id, "assistant", text))
        elif btype == "tool-call":
            # Committed tool-call on the message — tool/call event is the source
            # of truth; skip the duplicate block.
            continue
    return seq


def _parse_tool_result(data: dict[str, Any]) -> tuple[str, str, bool]:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    source = message.get("source") if isinstance(message.get("source"), dict) else {}
    call_id = str(source.get("callId") or "")
    parts: list[str] = []
    is_error = False
    content = message.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if not call_id:
                call_id = str(item.get("toolCallId") or "")
            if item.get("isError"):
                is_error = True
            inner = item.get("content")
            if isinstance(inner, list):
                for block in inner:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
            elif isinstance(inner, str):
                parts.append(inner)
    return call_id, "".join(parts), is_error


def _attach_timing(ev: dict[str, Any], *sources: Any) -> None:
    at = _coerce_event_at(*sources)
    if at and "at" not in ev:
        ev["at"] = at
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("elapsed_ms", "elapsedMs", "duration_ms", "durationMs"):
            if "elapsed_ms" in ev:
                break
            val = src.get(key)
            if isinstance(val, bool) or not isinstance(val, int | float):
                continue
            if not math.isfinite(val) or val < 0:
                continue
            ev["elapsed_ms"] = float(val)
        started = src.get("started_at") or src.get("startedAt")
        if isinstance(started, str) and started.strip() and "started_at" not in ev:
            ev["started_at"] = started.strip()
        ended = src.get("ended_at") or src.get("endedAt")
        if isinstance(ended, str) and ended.strip():
            ev["ended_at"] = ended.strip()


def _coerce_event_at(*sources: Any) -> str | None:
    """Vendor clock first (timestamp / epoch ``time``), then receive-time ``at``."""
    strings: list[str] = []
    epoch_iso: str | None = None
    receive: str | None = None
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("timestamp", "created_at", "started_at"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                strings.append(val.strip())
        iso = _epoch_to_iso(src.get("time"))
        if iso and epoch_iso is None:
            epoch_iso = iso
        at = src.get("at")
        if isinstance(at, str) and at.strip() and receive is None:
            receive = at.strip()
    if strings:
        return strings[0]
    return epoch_iso or receive


def _epoch_to_iso(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    ms = float(value)
    if ms < 1e11:
        ms *= 1000.0
    try:
        parsed = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    stamp = parsed.strftime("%Y-%m-%dT%H:%M:%S")
    if parsed.microsecond:
        stamp = f"{stamp}.{parsed.microsecond:06d}".rstrip("0")
    return stamp + "Z"


def _iso_delta_ms(started: str, ended: str) -> float | None:
    a = _parse_iso(started)
    b = _parse_iso(ended)
    if a is None or b is None:
        return None
    delta = (b - a).total_seconds() * 1000.0
    if delta < 0:
        return 0.0
    return round(delta, 3)


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _unwrap_event(raw: dict[str, Any]) -> dict[str, Any]:
    inner = raw.get("event")
    if isinstance(inner, dict) and ("type" in inner or "data" in inner):
        return inner
    return raw


def _text(seq: int, session_id: str, channel: str, text: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "seq": seq,
        "session_id": session_id,
        "source": _SOURCE,
        "kind": "text",
        "channel": channel,
        "text": text,
    }


def _as_args(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _tool_kind(name: str) -> str:
    lowered = name.lower()
    if any(n in lowered for n in ("bash", "shell", "exec", "python")):
        return "execute"
    if any(n in lowered for n in ("read", "cat", "view")):
        return "read"
    if any(n in lowered for n in ("write", "edit", "str_replace")):
        return "edit"
    return "other"


def _normalize_usage(raw: dict[str, Any]) -> dict[str, Any]:
    def _int(keys: tuple[str, ...]) -> int | None:
        for key in keys:
            val = raw.get(key)
            if isinstance(val, bool):
                continue
            if isinstance(val, (int, float)):
                return int(val)
        return None

    out: dict[str, Any] = {}
    inp = _int(("input_tokens", "inputTokens"))
    outp = _int(("output_tokens", "outputTokens"))
    cache = _int(("cache_read_tokens", "cacheReadTokens"))
    reason = _int(("reasoning_tokens", "reasoningTokens"))
    if inp is not None:
        out["input_tokens"] = inp
    if outp is not None:
        out["output_tokens"] = outp
    if inp is not None or outp is not None:
        out["total_tokens"] = (inp or 0) + (outp or 0)
    if cache is not None:
        out["cache_read_tokens"] = cache
    if reason is not None:
        out["reasoning_tokens"] = reason
    return out


def _clip(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        blob = json.dumps(raw, ensure_ascii=False, default=str)
    except TypeError:
        return {"repr": str(raw)[:_OPAQUE_CLIP]}
    if len(blob) <= _OPAQUE_CLIP:
        return raw
    return {"clipped": True, "preview": blob[:_OPAQUE_CLIP]}
