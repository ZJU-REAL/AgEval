"""RunTerminal — Run completion reason only (never PASS/score)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunTerminalKind(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunTerminal:
    """Typed run end state. ``completed`` is not a Benchmark PASS."""

    kind: RunTerminalKind
    reason: str = ""

    @staticmethod
    def completed(reason: str = "ok") -> RunTerminal:
        return RunTerminal(kind=RunTerminalKind.COMPLETED, reason=reason)

    @staticmethod
    def failed(reason: str) -> RunTerminal:
        return RunTerminal(kind=RunTerminalKind.FAILED, reason=reason)

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "reason": self.reason}
