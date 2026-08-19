"""Parse ``agent_ref`` and resolve the Agent package root (design/14).

``agent_ref`` is provenance injected by ``--agent``. Overlay bytes listed on
that binding resolve only against this package, never the Dataset tree.
"""

from __future__ import annotations

from pathlib import Path

from bora.agents.store import resolve_installed_ref
from bora.config.errors import (
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_MISSING_REFERENCE,
    ConfigError,
)

_FILE_PREFIX = "file:"
_DEV_PLUS = "@dev+"
_DEV_SUFFIX = "@dev"
_SHA_PREFIX = "sha256:"
_LOCAL_PREFIX = "local/"


def published_agent_ref_parts(ref: object) -> tuple[str, str] | None:
    """Hub-publishable ``(org/name, version)`` from an ``agent_ref``.

    ``file:`` and ``local/`` refs return ``None`` — they must not create
    Hub appearances (design/12, design/14).
    """
    if not isinstance(ref, str):
        return None
    text = ref.strip()
    if not text or text.startswith(_FILE_PREFIX):
        return None
    at = text.find("@")
    if at <= 0:
        return None
    package_id = text[:at]
    if "/" not in package_id or package_id.startswith(_LOCAL_PREFIX):
        return None
    rest = text[at + 1 :]
    plus = rest.find("+")
    version = (rest[:plus] if plus >= 0 else rest).strip()
    if not version:
        return None
    return package_id, version


def package_root_from_agent_ref(ref: str) -> Path:
    """Return the installed (or ``file:``) Agent package root. Fail closed."""
    text = ref.strip()
    if not text:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_ref must not be empty",
            location="/agent_ref",
        )
    if text.startswith(_FILE_PREFIX):
        return _file_package_root(text)
    return _cache_package_root(text)


def _file_package_root(ref: str) -> Path:
    rest = ref[len(_FILE_PREFIX) :]
    if _DEV_PLUS in rest:
        path_s = rest.rsplit(_DEV_PLUS, 1)[0]
    elif rest.endswith(_DEV_SUFFIX):
        path_s = rest[: -len(_DEV_SUFFIX)]
    else:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "file: agent_ref must be file:<path>@dev[+sha256:…]",
            location=ref,
        )
    if not path_s:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "file: agent_ref is missing a path",
            location=ref,
        )
    path = Path(path_s).expanduser()
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        raise ConfigError(
            ERROR_MISSING_REFERENCE,
            f"agent package not found for agent_ref: {path_s}",
            location=ref,
        )
    return path.resolve(strict=False)


def _cache_package_root(ref: str) -> Path:
    id_ver, plus, digest = ref.partition("+")
    agent_id, at, version = id_ver.rpartition("@")
    if not at or not agent_id.strip() or not version.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_ref must be <id>@<version>+sha256:…",
            location=ref,
        )
    entry, root = resolve_installed_ref(agent_id.strip(), version.strip())
    if plus and digest.strip():
        want = digest.strip()
        hex_want = want[len(_SHA_PREFIX) :] if want.startswith(_SHA_PREFIX) else want
        have = entry.digest
        hex_have = have[len(_SHA_PREFIX) :] if have.startswith(_SHA_PREFIX) else have
        if not hex_have.startswith(hex_want):
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "agent_ref digest does not match the installed package",
                location=ref,
            )
    return root
