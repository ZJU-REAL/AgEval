"""Cancellation signal observed by the Attempt host."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CancellationSignal:
    """Cooperative cancellation flag observed by the Coordinator."""

    _cancelled: bool = field(default=False, init=False)
    reason: str = "user_cancel"

    def cancel(self, reason: str = "user_cancel") -> None:
        self._cancelled = True
        self.reason = reason

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
