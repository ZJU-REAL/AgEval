"""Schema constants and helpers for Attempt evidence / invocation trajectory."""

from __future__ import annotations

from typing import Any, Final, Literal

EVENT_SCHEMA_VERSION: Final[str] = "ageval.trajectory.event/1"
METADATA_SCHEMA_VERSION: Final[str] = "ageval.trajectory.metadata/1"
SUMMARY_SCHEMA_VERSION: Final[str] = "ageval.evidence.summary/1"

InvocationStatus = Literal[
    "running",
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "crash",
    "redaction_failed",
]

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "completed",
        "failed",
        "timeout",
        "cancelled",
        "crash",
        "redaction_failed",
    }
)


def invocation_dir_name(seq: int, invocation_id: str) -> str:
    """Zero-padded sequence + id, e.g. ``0001-inv_abc``."""
    if seq < 1:
        raise ValueError("invocation sequence must be >= 1")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in invocation_id)
    return f"{seq:04d}-{safe}"


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def normalize_event(event: dict[str, Any], *, seq: int) -> dict[str, Any]:
    """Attach ageval envelope fields without discarding backend payload."""
    out = dict(event)
    out.setdefault("schema", EVENT_SCHEMA_VERSION)
    out["seq"] = seq
    if "type" not in out:
        out["type"] = str(event.get("kind") or event.get("event") or "backend")
    return out
