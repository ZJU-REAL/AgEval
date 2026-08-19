"""Attempt phase wall-time, for job views and progress bars.

Observational only — never PASS authority, never part of a fingerprint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

TIMING_SCHEMA = "ageval.phase_timing/1"

# Canonical order for bars / summary.
STANDARD_PHASES: tuple[str, ...] = ("environment", "run", "evaluate", "record", "cleanup")

PHASE_LABELS: dict[str, str] = {
    "environment": "Env Setup",
    "run": "Agent Execution",
    "evaluate": "Verifier",
    "record": "Trajectory",
    "cleanup": "Cleanup",
}


def timing_from_facts(facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the timing block from ``phase_finished`` facts, in phase order."""
    totals: dict[str, float] = {}
    for fact in facts:
        if fact.get("name") != "phase_finished":
            continue
        detail = fact.get("detail")
        if not isinstance(detail, Mapping):
            continue
        phase = str(detail.get("phase") or "")
        duration = detail.get("duration_ms")
        if not phase or not isinstance(duration, int | float) or isinstance(duration, bool):
            continue
        totals[phase] = totals.get(phase, 0.0) + float(duration)

    ordered = [p for p in STANDARD_PHASES if p in totals]
    ordered.extend(sorted(p for p in totals if p not in STANDARD_PHASES))
    phases = [
        {"id": name, "label": PHASE_LABELS.get(name, name), "duration_ms": round(totals[name], 3)}
        for name in ordered
    ]
    return {
        "schema": TIMING_SCHEMA,
        "phases": phases,
        "total_ms": round(sum(float(p["duration_ms"]) for p in phases), 3),
    }


def format_duration_ms(ms: float | None) -> str | None:
    """Human label like Harbor (``1m 12s``, ``4m 27s``, ``830ms``)."""
    if ms is None or not isinstance(ms, int | float) or isinstance(ms, bool):
        return None
    if ms < 0:
        ms = 0.0
    if ms < 1000:
        return f"{int(round(ms))}ms"
    total_s = ms / 1000.0
    if total_s < 60:
        if total_s < 10:
            return f"{total_s:.1f}s"
        return f"{int(round(total_s))}s"
    minutes = int(total_s // 60)
    seconds = int(round(total_s - minutes * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}m {seconds:02d}s" if seconds else f"{minutes}m"
