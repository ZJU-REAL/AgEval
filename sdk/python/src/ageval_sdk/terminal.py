"""HarnessTerminal — Harness completion reason only (never PASS/score)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HarnessTerminalKind(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class HarnessTerminal:
    """Typed Harness end state. ``completed`` is not a Benchmark PASS."""

    kind: HarnessTerminalKind
    reason: str = ""

    @staticmethod
    def completed(reason: str = "ok") -> HarnessTerminal:
        return HarnessTerminal(kind=HarnessTerminalKind.COMPLETED, reason=reason)

    @staticmethod
    def failed(reason: str) -> HarnessTerminal:
        return HarnessTerminal(kind=HarnessTerminalKind.FAILED, reason=reason)

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "reason": self.reason}
