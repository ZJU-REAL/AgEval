"""Capability denial errors (fail-closed before external effect)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityError(Exception):
    error_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


ERROR_CLOSED = "closed"
ERROR_CROSS_ATTEMPT = "cross_attempt"
ERROR_UNDECLARED = "undeclared"
ERROR_QUOTA_EXCEEDED = "quota_exceeded"
ERROR_UNAVAILABLE = "capability_unavailable"
ERROR_INVALID = "invalid_capability"
