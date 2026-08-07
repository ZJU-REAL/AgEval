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
) -> Path:
    """Write **turn-level** training trajectory for one BORA invoke.

    One ``session/prompt`` (one invoke) → one training turn unit:

    1. ``user`` — full prompt
    2. ``assistant`` (optional ``part=thought``) — merged thought text
    3. ``assistant`` — merged message text (prefer ``final_text``)
    4. ``terminal`` — ok / error / structured / usage / stop metadata

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
    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    return path
