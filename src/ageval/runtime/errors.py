"""Lifecycle Core error types (fail-closed before mutation)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LifecycleError(Exception):
    """Stable lifecycle failure with an operator-facing code."""

    error_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


ERROR_ILLEGAL_TRANSITION = "illegal_transition"
ERROR_CROSS_ATTEMPT = "cross_attempt"
ERROR_INVALID_IDENTITY = "invalid_identity"
ERROR_INVALID_RETRY = "invalid_retry"
ERROR_TERMINAL_REOPEN = "terminal_reopen"
ERROR_DUPLICATE_STAGE = "duplicate_stage"
ERROR_INVALID_ARGUMENT = "invalid_argument"
