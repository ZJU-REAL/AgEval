"""Domain errors for Registry services. Handler maps these to JSON HTTP."""

from __future__ import annotations

from typing import Any


class RegistryAppError(Exception):
    """Business failure with a stable error code and HTTP status."""

    def __init__(
        self,
        error: str,
        message: str,
        *,
        http_status: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.http_status = http_status
        self.extra = extra or {}

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error": self.error, "message": self.message}
        out.update(self.extra)
        return out
