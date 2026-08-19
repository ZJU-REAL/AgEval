"""Credential projection for an ACP entry process.

Only credentials and the non-secret upstream URL come from the host here. Paths
(``PATH``, ``HOME``, ``XDG_*``) belong to the box and to ``home.py`` — copying a
host path into a box is how an engine ends up trying to write ``/Users`` inside
a container.

The profile carries a *locator*: ``api_key`` names a host env var, never a
value. Values are read at spawn time, never logged, never written to the lock.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

# Profile ``base_url`` projects into both stacks; the entry reads whichever it uses.
_BASE_URL_ENV_NAMES: tuple[str, ...] = ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL")

# A profile api_key is one secret with many vendor names. These are the names an
# entry may read it under, so one locator covers the entry's own convention.
_API_KEY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "pi": (
        # Z.AI coding plan (global vs China — the provider picks which it reads)
        "ZAI_API_KEY",
        "ZAI_CODING_CN_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
    ),
    "opencode": (
        "ZHIPU_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENCODE_API_KEY",
    ),
    "claude-code": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY",),
    "grok-build": ("XAI_API_KEY",),
}


def project_credential_env(
    entry_id: str,
    *,
    credential_env_names: Sequence[str],
    api_key_env: str | None = None,
    base_url: str | None = None,
    host_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Allowlisted credential env for one entry process (empty values dropped)."""
    host = host_environ if host_environ is not None else os.environ
    env: dict[str, str] = {}

    if base_url:
        for name in _BASE_URL_ENV_NAMES:
            env[name] = base_url

    for name in credential_env_names:
        value = host.get(name)
        if value:
            env[name] = value

    if api_key_env:
        value = host.get(api_key_env)
        if value:
            env[api_key_env] = value
            for alias in _API_KEY_ALIASES.get(entry_id, ()):
                env.setdefault(alias, value)

    return {key: value for key, value in env.items() if value}


def entry_credentials_missing(
    credential_env_names: Sequence[str],
    *,
    api_key_env: str | None = None,
    host_environ: Mapping[str, str] | None = None,
) -> bool:
    """True when no declared locator or credential name has a value.

    An entry that declares no credential name (OAuth-only) is never "missing".
    Values are never returned.
    """
    host = host_environ if host_environ is not None else os.environ
    if api_key_env and str(host.get(api_key_env) or "").strip():
        return False
    names = [name for name in credential_env_names if name]
    if not names:
        return False
    return not any(str(host.get(name) or "").strip() for name in names)
