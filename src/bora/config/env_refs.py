"""Profile binding ``${ENV_NAME}`` refs.

``api_key: ${NAME}`` unwraps to locator ``NAME`` (secret value never enters the
binding). ``base_url: ${NAME}`` substitutes the host env value. Bare locator
names are rejected.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from bora.config.errors import ERROR_INVALID_SCHEMA, ConfigError

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def parse_env_ref(raw: str) -> str | None:
    text = raw.strip()
    match = _ENV_REF.fullmatch(text)
    return match.group(1) if match else None


def expand_api_key_locator(raw: str, *, location: str) -> str:
    name = parse_env_ref(raw)
    if name is None:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "profile.api_key must be ${ENV_NAME} (env locator; never a bare name or secret)",
            location=location,
        )
    return name


def expand_base_url_value(
    raw: str,
    *,
    location: str,
    environ: Mapping[str, str] | None = None,
) -> str:
    name = parse_env_ref(raw)
    if name is None:
        return raw.strip()
    env = os.environ if environ is None else environ
    val = env.get(name)
    if not val or not str(val).strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"profile.base_url ${{{name}}} is unset (set it in process env or package/repo .env)",
            location=location,
        )
    return str(val).strip()


def expand_binding_env_refs(
    binding: dict[str, Any],
    *,
    location: str,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Rewrite api_key / base_url ${} refs in place on one binding."""
    api_key = binding.get("api_key")
    if api_key is not None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile.api_key must be a non-empty ${ENV_NAME} when set",
                location=f"{location}/api_key",
            )
        binding["api_key"] = expand_api_key_locator(api_key, location=f"{location}/api_key")
    base_url = binding.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile.base_url must be a non-empty string when set",
                location=f"{location}/base_url",
            )
        binding["base_url"] = expand_base_url_value(
            base_url,
            location=f"{location}/base_url",
            environ=environ,
        )
