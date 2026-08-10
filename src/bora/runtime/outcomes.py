"""Immutable phase facts, events, and Attempt records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from bora.runtime.identity import AttemptIdentity
from bora.runtime.lifecycle import LifecyclePhase, LifecycleState


class RuntimeTerminalKind(StrEnum):
    """Primary Runtime terminal for an Attempt (not a Benchmark PASS/FAIL)."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class PhaseStatus(StrEnum):
    """Status of a single generic stage fact."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class PhaseFact:
    """Identity-bound generic stage fact (no score/PASS)."""

    attempt: AttemptIdentity
    phase: LifecyclePhase
    status: PhaseStatus
    message: str = ""
    detail: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    # Wall time for this stage in milliseconds (#47 D); observational only.
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        # Freeze nested detail mapping.
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """Append-only transition event."""

    attempt: AttemptIdentity
    sequence: int
    from_state: LifecycleState
    to_state: LifecycleState
    reason: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Immutable Attempt aggregate returned by the Coordinator."""

    attempt: AttemptIdentity
    state: LifecycleState
    terminal: RuntimeTerminalKind | None
    events: tuple[LifecycleEvent, ...]
    phase_facts: tuple[PhaseFact, ...]
    cleanup_calls: int
    cleanup_warning: str | None = None

    def snapshot(self) -> AttemptRecord:
        """Return self — records are already immutable."""
        return self
