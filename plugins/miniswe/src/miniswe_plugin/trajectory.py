"""Map mini-swe-agent messages to ``bora.trajectory.event/1``.

No ACP ``session_update`` shapes. Importable without BORA Core.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "bora.trajectory.event/1"
_SOURCE = "miniswe"


def to_bora_trajectory_events(
    messages: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    session_id: str = "miniswe",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seq = 0
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "")
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        actions = extra.get("actions") if isinstance(extra.get("actions"), list) else []
        if role in {"system", "user"}:
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": role,
                    "text": str(raw.get("content") or "")[:8000],
                }
            )
            continue
        if role == "assistant":
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": "assistant",
                    "text": str(raw.get("content") or "")[:8000],
                }
            )
            for i, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                seq += 1
                cmd = str(action.get("command") or action.get("cmd") or "")
                out.append(
                    {
                        "schema": SCHEMA,
                        "seq": seq,
                        "session_id": session_id,
                        "source": _SOURCE,
                        "kind": "tool",
                        "name": "bash",
                        "call_id": f"miniswe_{seq}_{i}",
                        "arguments": {"command": cmd},
                    }
                )
            continue
        if role in {"tool", "user"} and extra.get("returncode") is not None:
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "observation",
                    "name": "bash",
                    "text": str(raw.get("content") or extra.get("output") or "")[:8000],
                }
            )
            continue
        if role == "exit":
            seq += 1
            out.append(
                {
                    "schema": SCHEMA,
                    "seq": seq,
                    "session_id": session_id,
                    "source": _SOURCE,
                    "kind": "text",
                    "channel": "exit",
                    "text": str(raw.get("content") or extra.get("exit_status") or ""),
                }
            )
    return out
