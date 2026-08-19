"""Cancellation signal and monotonic clock helpers for Lifecycle Coordinator."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

MonotonicClock = Callable[[], float]


def default_monotonic_clock() -> float:
    """Production monotonic clock (seconds)."""
    return time.monotonic()


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
