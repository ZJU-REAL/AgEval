"""Map wrapper-emitted ACP events to ``ageval.trajectory.event/1``.

Vendor CLI logs are never scraped. Importable without ageval Core.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "ageval.trajectory.event/1"
_SOURCE = "acp-oneshot"


def to_ageval_trajectory_events(
    raw_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    session_id: str = "acp-oneshot",
) -> list[dict[str, Any]]:
    """Wrapper events → Core-owned trajectory rows with this plugin as source."""
    out: list[dict[str, Any]] = []
    seq = 0
    sid_fallback = session_id

    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        if raw.get("schema") == SCHEMA:
            row = dict(raw)
            row["source"] = _SOURCE
            seq += 1
            row["seq"] = seq
            out.append(row)
            continue

        sid = raw.get("session_id") if isinstance(raw.get("session_id"), str) else sid_fallback
        if raw.get("type") == "permission_decision":
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
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

        channel = raw.get("channel")
        text = raw.get("text")
        if channel in {"thought", "assistant"} and isinstance(text, str):
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": sid,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": channel,
                    "text": text,
                }
            )

        raw_upd = raw.get("update")
        upd: dict[str, Any] = raw_upd if isinstance(raw_upd, dict) else {}
        session_upd = (
            upd.get("sessionUpdate") or upd.get("session_update") or raw.get("session_update")
        )
        if session_upd not in {"tool_call", "tool_call_update"}:
            continue
        call_id = upd.get("toolCallId") or upd.get("tool_call_id") or raw.get("tool_call_id")
        if not call_id:
            continue
        seq += 1
        out.append(
            {
                "schema": SCHEMA,
                "seq": seq,
                "session_id": sid,
                "source": _SOURCE,
                "kind": "tool",
                "tool_call_id": str(call_id),
                "title": upd.get("title") or raw.get("title"),
                "status": upd.get("status") or raw.get("status"),
            }
        )
    return out
