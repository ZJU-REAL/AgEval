"""Config Core error types.

Every failure that must reach the operator maps to a stable ``error_code`` and
CLI exit 2. Messages may include JSON Pointers or package-relative paths; they
must never include host secrets or raw stack traces on the public path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfigError(Exception):
    """Fail-closed Config error with a stable operator-facing code."""

    error_code: str
    message: str
    location: str | None = None

    def __str__(self) -> str:
        if self.location:
            return f"{self.error_code}: {self.message} ({self.location})"
        return f"{self.error_code}: {self.message}"


# Stable codes required by Spec 00 / Roadmap v0.1.
ERROR_INVALID_PACKAGE = "invalid_package"
ERROR_INVALID_FORMAT = "invalid_format"
ERROR_UNKNOWN_TASK = "unknown_task"
ERROR_UNKNOWN_PROFILE = "unknown_profile"
ERROR_UNSUPPORTED_CAPABILITY = "unsupported_capability"
ERROR_PATH_OUTSIDE_PACKAGE = "path_outside_package"
ERROR_UNKNOWN_PACKAGE_PATH = "unknown_package_path"
ERROR_INVALID_OVERRIDE = "invalid_override"
ERROR_INVALID_SCHEMA = "invalid_schema"
ERROR_MISSING_REFERENCE = "missing_reference"
