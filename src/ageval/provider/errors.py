"""Provider typed errors (fail-closed before spawn when possible)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderError(Exception):
    error_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


ERROR_INVALID_WORKDIR = "outside_workdir"
ERROR_UNDECLARED_EXECUTABLE = "undeclared_executable"
ERROR_INVALID_PLAN = "invalid_plan"
ERROR_SPAWN_FAILED = "spawn_failed"
ERROR_CROSS_ATTEMPT = "cross_attempt_handle"
ERROR_ALREADY_CLEANED = "already_cleaned"
