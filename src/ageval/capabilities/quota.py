"""Shared Agent invocation quota — one counter for Capability API and Agent Service.

ParentAgentService and AttemptCapabilityAuthority must not keep parallel
``_remaining`` / ``_agent_used`` ledgers for the same Attempt.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class AgentInvocationQuota:
    """Thread-safe pre-effect invoke budget (no refund on failure)."""

    limit: int
    _used: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self.limit = max(0, int(self.limit))

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.limit - self._used)

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def try_consume(self) -> bool:
        """Reserve one slot. Returns False when the ceiling is already exhausted."""
        with self._lock:
            if self._used >= self.limit:
                return False
            self._used += 1
            return True
