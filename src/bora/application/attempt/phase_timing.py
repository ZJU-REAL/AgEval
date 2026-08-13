"""Attempt / job phase wall-time recording (#47 D).

Standard display phases (Harbor-like labels; BORA keys underneath):

- ``prepare``  — Env / lock / provider / agent service setup
- ``run``      — Harness (agent execution)
- ``evaluate`` — Seal inputs + independent evaluator (+ bind)
- ``cleanup``  — Teardown

Metrics are observational only — never PASS authority, never fingerprint.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

# Canonical order for bars / summary.
STANDARD_PHASES: tuple[str, ...] = ("prepare", "run", "evaluate", "cleanup")

# Harbor-ish labels for UI (keys stay stable for APIs).
PHASE_LABELS: dict[str, str] = {
    "prepare": "Env Setup",
    "run": "Agent Execution",
    "evaluate": "Verifier",
    "cleanup": "Cleanup",
    # Lifecycle-internal names (coordinator) map into the four buckets.
    "seal": "Verifier",
    "bind": "Verifier",
}

# Map fine-grained lifecycle phases → display buckets.
_BUCKET: dict[str, str] = {
    "prepare": "prepare",
    "run": "run",
    "seal": "evaluate",
    "evaluate": "evaluate",
    "bind": "evaluate",
    "cleanup": "cleanup",
}


@dataclass
class PhaseTimer:
    """Accumulate wall durations for named phases (monotonic clock)."""

    _clock: Any = field(default=time.monotonic, repr=False)
    _segments: dict[str, float] = field(default_factory=dict)
    _started_at_wall: float | None = None
    _finished_at_wall: float | None = None

    def __post_init__(self) -> None:
        self._started_at_wall = time.time()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Time a phase; nested/re-entry adds to the same key."""
        key = str(name or "").strip() or "unknown"
        t0 = self._clock()
        try:
            yield
        finally:
            dt_ms = max(0.0, (self._clock() - t0) * 1000.0)
            self._segments[key] = self._segments.get(key, 0.0) + dt_ms

    def add_ms(self, name: str, duration_ms: float) -> None:
        key = str(name or "").strip() or "unknown"
        if duration_ms < 0:
            duration_ms = 0.0
        self._segments[key] = self._segments.get(key, 0.0) + float(duration_ms)

    def finish(self) -> None:
        self._finished_at_wall = time.time()

    def as_dict(self) -> dict[str, Any]:
        """Serializable ``phase_timing`` block for result / summary / suite."""
        self.finish()
        phases = [
            {
                "id": name,
                "label": PHASE_LABELS.get(name, name),
                "duration_ms": round(self._segments.get(name, 0.0), 3),
            }
            for name in STANDARD_PHASES
            if name in self._segments
        ]
        # Include any non-standard keys (e.g. environment-only) after standard.
        for name, ms in self._segments.items():
            if name in STANDARD_PHASES:
                continue
            phases.append(
                {
                    "id": name,
                    "label": PHASE_LABELS.get(name, name),
                    "duration_ms": round(ms, 3),
                }
            )
        total = sum(float(p["duration_ms"]) for p in phases)
        return {
            "schema": "bora.phase_timing/1",
            "phases": phases,
            "total_ms": round(total, 3),
            "started_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._started_at_wall))
                if self._started_at_wall is not None
                else None
            ),
            "finished_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._finished_at_wall))
                if self._finished_at_wall is not None
                else None
            ),
        }


def bucket_phase_timing(raw_phases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse fine-grained phase rows into the four display buckets."""
    buckets: dict[str, float] = {k: 0.0 for k in STANDARD_PHASES}
    for row in raw_phases:
        if not isinstance(row, Mapping):
            continue
        pid = str(row.get("id") or row.get("phase") or "").strip()
        ms = row.get("duration_ms")
        if not isinstance(ms, int | float) or isinstance(ms, bool):
            continue
        bucket = _BUCKET.get(pid, pid if pid in STANDARD_PHASES else None)
        if bucket is None:
            continue
        buckets[bucket] = buckets.get(bucket, 0.0) + float(ms)
    phases = [
        {
            "id": name,
            "label": PHASE_LABELS.get(name, name),
            "duration_ms": round(buckets[name], 3),
        }
        for name in STANDARD_PHASES
        if buckets.get(name, 0.0) > 0 or name in buckets
    ]
    # Drop zero-only trailing noise: keep zeros only if something else exists.
    if any(p["duration_ms"] > 0 for p in phases):
        phases = [p for p in phases if p["duration_ms"] > 0 or p["id"] in ("prepare", "run")]
    total = sum(float(p["duration_ms"]) for p in phases)
    return {
        "schema": "bora.phase_timing/1",
        "phases": phases,
        "total_ms": round(total, 3),
    }


def phase_facts_to_timing(phase_facts: Sequence[Any]) -> dict[str, Any]:
    """Build phase_timing from coordinator ``PhaseFact`` rows (duration_ms field)."""
    rows: list[dict[str, Any]] = []
    for fact in phase_facts:
        phase = getattr(fact, "phase", None)
        # Enum PhaseFact.phase → .value; avoid optional member access for pyright.
        raw_id = getattr(phase, "value", None) if phase is not None else None
        pid = str(raw_id if raw_id is not None else (phase or ""))
        ms = getattr(fact, "duration_ms", None)
        if ms is None:
            detail = getattr(fact, "detail", None) or {}
            if isinstance(detail, Mapping):
                ms = detail.get("duration_ms")
        if not isinstance(ms, int | float) or isinstance(ms, bool):
            continue
        rows.append({"id": pid, "duration_ms": float(ms)})
    return bucket_phase_timing(rows)


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
