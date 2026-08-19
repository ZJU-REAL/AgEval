"""Shared L0 CLI child-env projection (allowlisted keys only).

Profile fields:
- ``base_url``: non-secret URL → common provider base-url env names
- ``api_key`` / ``api_key_env``: host env *locator name* → value projected + aliases

Values are never logged here. Not for L1 mount projection (see credential_projection).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Final

from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES

# Always present for CLI subprocesses (empty values dropped at the end).
_CORE_HOST_KEYS: Final[tuple[str, ...]] = ("PATH", "HOME", "LANG")

# ACP entry_id (and historical kind aliases) → extra host keys to copy when set.
_KIND_EXTRA_HOST_KEYS: Final[Mapping[str, tuple[str, ...]]] = {
    "pi": ("PI_OFFLINE",),
    "opencode": ("XDG_DATA_HOME", "XDG_CONFIG_HOME"),
    "claude-code": (),
    "codex": (),
    "grok-build": (),
}

# Fallback credential env allowlists keyed by ACP entry_id (Spec 19).
_ENTRY_CREDENTIAL_ENV: Final[Mapping[str, tuple[str, ...]]] = {
    "codex": (),
    "pi": (
        "ZAI_API_KEY",
        "ZAI_CODING_CN_API_KEY",
        "ZHIPU_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "XAI_API_KEY",
    ),
    "opencode": (
        "ZHIPU_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENCODE_API_KEY",
        "XAI_API_KEY",
    ),
    "claude-code": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "grok-build": ("XAI_API_KEY",),
}

# Profile base_url projects into these (CLI may use either stack).
_BASE_URL_ENV_NAMES: Final[tuple[str, ...]] = (
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
)

# When host lacks ZAI_API_KEY, promote these aliases (pi/Zhipu coding plan).
_ZAI_HOST_ALIASES: Final[tuple[str, ...]] = (
    "ZHIPU_API_KEY",
    "zhipu_coding_api_key",
    "ZHIPU_CODING_API_KEY",
    "glm_coding_api_key",
)

# Profile api_key value also setdefault into these provider-standard names.
_KIND_API_KEY_ALIASES: Final[Mapping[str, tuple[str, ...]]] = {
    "pi": (
        # Z.AI coding plan (global vs China — provider picks which it reads)
        "ZAI_API_KEY",
        "ZAI_CODING_CN_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        # only if model actually resolves to opencode/* catalog
        "OPENCODE_API_KEY",
    ),
    "opencode": (
        "ZHIPU_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENCODE_API_KEY",
    ),
    "claude-code": (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    ),
}


def project_cli_child_env(
    kind: str,
    *,
    api_key_env: str | None = None,
    base_url: str | None = None,
    host_environ: Mapping[str, str] | None = None,
    credential_env_names: Sequence[str] | None = None,
    extra_host_keys: Sequence[str] | None = None,
    api_key_aliases: Sequence[str] | None = None,
) -> dict[str, str]:
    """Build allowlisted env for a CLI agent subprocess.

    Parameters
    ----------
    kind:
        Executor kind (``pi`` / ``opencode`` / ``claude-code`` / …). Used to
        resolve default credential names and aliases from the capability matrix.
    api_key_env:
        Profile locator: name of a host env var holding the secret (not the value).
    base_url:
        Optional non-secret upstream URL from the locked profile.
    host_environ:
        Override host env (tests); defaults to ``os.environ``.
    """
    host = host_environ if host_environ is not None else os.environ
    caps = BUILTIN_CAPABILITIES.get(kind)
    if credential_env_names is not None:
        cred_names = tuple(credential_env_names)
    elif caps is not None and caps.credential_env_names:
        cred_names = tuple(caps.credential_env_names)
    else:
        # ACP entry ids (codex/pi/opencode/…) carry allowlists here.
        try:
            from bora.plugins.contrib.acp.registry import get_entry

            desc = get_entry(kind)
            if desc is not None:
                cred_names = tuple(desc.credential_env_names)
            else:
                cred_names = tuple(_ENTRY_CREDENTIAL_ENV.get(kind, ()))
        except Exception:  # noqa: BLE001 — registry optional in early import
            cred_names = tuple(_ENTRY_CREDENTIAL_ENV.get(kind, ()))
    extras: tuple[str, ...] = (
        tuple(extra_host_keys)
        if extra_host_keys is not None
        else tuple(_KIND_EXTRA_HOST_KEYS.get(kind, ()))
    )
    aliases: tuple[str, ...] = (
        tuple(api_key_aliases)
        if api_key_aliases is not None
        else tuple(_KIND_API_KEY_ALIASES.get(kind, ()))
    )

    env: dict[str, str] = {
        "PATH": host.get("PATH", ""),
        "HOME": host.get("HOME", ""),
        "LANG": host.get("LANG", "C"),
        "TERM": "dumb",
    }
    for key in extras:
        val = host.get(key, "")
        if val:
            env[key] = val

    # base_url (profile) wins; else pass through host ANTHROPIC_BASE_URL if present.
    if base_url:
        for name in _BASE_URL_ENV_NAMES:
            env.setdefault(name, base_url)
    else:
        for name in _BASE_URL_ENV_NAMES:
            if host.get(name):
                env[name] = host[name]

    # Zhipu / coding-plan aliases → ZAI (pi-oriented; harmless no-op for others).
    if kind == "pi" and not host.get("ZAI_API_KEY"):
        for alias in _ZAI_HOST_ALIASES:
            if host.get(alias):
                env["ZAI_API_KEY"] = host[alias]
                break

    for name in cred_names:
        val = host.get(name)
        if val:
            env[name] = val

    if api_key_env:
        val = host.get(api_key_env)
        if val:
            env[api_key_env] = val
            for alias in aliases:
                env.setdefault(alias, val)

    # Drop empty strings so subprocess does not see blank credentials.
    return {k: v for k, v in env.items() if v}


def entry_credentials_missing(
    credential_env_names: Sequence[str],
    *,
    api_key_env: str | None = None,
    host_environ: Mapping[str, str] | None = None,
) -> bool:
    """True when no declared locator or credential env name has a value.

    Empty ``credential_env_names`` and no ``api_key_env`` is not missing
    (the entry does not declare an env key — e.g. OAuth-only).
    Values are never returned.
    """
    host = host_environ if host_environ is not None else os.environ
    if api_key_env and str(host.get(api_key_env) or "").strip():
        return False
    names = [n for n in credential_env_names if n]
    if not names:
        return False
    return not any(str(host.get(n) or "").strip() for n in names)


def cli_credential_available(
    kind: str,
    *,
    api_key_env: str | None = None,
    host_environ: Mapping[str, str] | None = None,
    extra_ok: bool = False,
) -> bool:
    """True if projected env has the profile locator or any default credential name.

    ``extra_ok`` lets callers treat residual host auth (e.g. opencode auth.json)
    as already satisfied without putting secrets in the returned env.
    """
    if extra_ok:
        return True
    env = project_cli_child_env(kind, api_key_env=api_key_env, host_environ=host_environ)
    if api_key_env and env.get(api_key_env):
        return True
    caps = BUILTIN_CAPABILITIES.get(kind)
    if caps is not None and caps.credential_env_names:
        names = caps.credential_env_names
    else:
        names = _ENTRY_CREDENTIAL_ENV.get(kind, ())
        try:
            from bora.plugins.contrib.acp.registry import get_entry

            desc = get_entry(kind)
            if desc is not None:
                names = desc.credential_env_names
        except Exception:  # noqa: BLE001
            pass
    return any(env.get(name) for name in names)


def cli_env_for_container(
    kind: str, *, api_key_env: str | None, base_url: str | None
) -> dict[str, str]:
    """Project host credentials into docker ``-e`` (values never logged).

    Never copy host ``PATH`` / ``HOME`` / ``XDG_*`` — those are macOS/Linux host
    paths and break in-container engines (e.g. opencode ``mkdir /Users``).
    Callers set container ``HOME`` / ``PATH`` after this returns.
    """
    if kind in {"codex"}:
        env: dict[str, str] = {}
        if api_key_env and os.environ.get(api_key_env):
            env[api_key_env] = os.environ[api_key_env]
            env.setdefault("OPENAI_API_KEY", os.environ[api_key_env])
        elif os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        return env
    projected = project_cli_child_env(
        kind if kind != "claude" else "claude-code",
        api_key_env=api_key_env,
        base_url=base_url,
    )
    host_path_denylist = {
        "PATH",
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
    }
    return {k: v for k, v in projected.items() if v and k not in host_path_denylist}
