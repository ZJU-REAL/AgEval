"""L0 process outcomes — never score/PASS."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from bora.runtime.identity import AttemptIdentity


class ProcessTerminalKind(StrEnum):
    """How the process ended from the Provider's view."""

    EXITED = "exited"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    SPAWN_FAILED = "spawn_failed"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    """Structured L0 process facts bound to an Attempt."""

    attempt: AttemptIdentity
    assurance: str
    terminal: ProcessTerminalKind
    exit_code: int | None
    signal: int | None
    stdout_summary: str
    stderr_summary: str
    truncated: bool
    pid: int | None
    pgid: int | None
    termination_actions: tuple[str, ...] = ()
    writer_stop_confirmed: bool = False
    cleanup_ok: bool = False
    cleanup_warning: str | None = None
    detail: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.assurance != "l0":
            # L0 provider must not claim higher assurance.
            object.__setattr__(self, "assurance", "l0")
