"""Shared Config validation helpers (single raise site per rule)."""

from __future__ import annotations

from typing import Any

from bora.config.errors import ERROR_INVALID_SCHEMA, ConfigError


def reject_env_interpolation(text: str, *, what: str, location: str) -> None:
    """Fail closed when yaml embeds env-style interpolation markers."""
    if "${" in text or "os.environ" in text:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"environment variable interpolation is not allowed in {what}",
            location=location,
        )


def require_agent_profiles_list(profiles: Any) -> list[Any]:
    """Return agent_profiles when it is a list; raise otherwise."""
    if not isinstance(profiles, list):
        raise ConfigError(
            ERROR_INVALID_SCHEMA, "agent_profiles must be a list", location="/agent_profiles"
        )
    return profiles
