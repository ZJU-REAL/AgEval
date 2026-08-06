"""PackageRef parsing for local paths and registry coordinates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bora.config.database import validate_database_id
from bora.config.errors import ConfigError

# identity@version  OR  identity@sha256:<64hex>
_REF_RE = re.compile(r"^(?P<id>[^@]+)@(?P<tail>.+)$")
_DIGEST_TAIL_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


@dataclass(frozen=True, slots=True)
class PackageRef:
    """Either a local Database path or a registry coordinate."""

    kind: str  # "path" | "version" | "digest"
    path: Path | None = None
    database_id: str | None = None
    version: str | None = None
    package_digest: str | None = None

    def display(self) -> str:
        if self.kind == "path":
            return str(self.path)
        if self.kind == "version":
            return f"{self.database_id}@{self.version}"
        return f"{self.database_id}@{self.package_digest}"


def parse_package_ref(raw: str | Path, *, cwd: Path | None = None) -> PackageRef:
    """Parse a CLI path/ref argument into a PackageRef.

    Existing directories are always treated as local paths (even if the string
    contains ``@``). Registry refs use ``database_id@version`` or
    ``database_id@sha256:<hex>``.
    """
    if isinstance(raw, Path):
        path = raw.expanduser()
        if not path.is_absolute() and cwd is not None:
            path = (cwd / path).resolve(strict=False)
        else:
            path = path.resolve(strict=False)
        if path.is_dir():
            return PackageRef(kind="path", path=path)
        raise ConfigError(
            "invalid_package",
            f"path is not a directory: {raw}",
            location=str(raw),
        )

    text = str(raw).strip()
    if not text:
        raise ConfigError("invalid_package", "empty package ref", location=str(raw))

    # Prefer local path when it exists as a directory.
    candidate = Path(text).expanduser()
    base = cwd or Path.cwd()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)
    if candidate.is_dir():
        return PackageRef(kind="path", path=candidate)

    m = _REF_RE.match(text)
    if not m:
        raise ConfigError(
            "invalid_package",
            "expected local Database path or <database_id>@<version|sha256:…>",
            location=text,
        )
    database_id = m.group("id")
    tail = m.group("tail")
    try:
        validate_database_id(database_id)
    except ConfigError as exc:
        raise ConfigError(
            "invalid_package",
            f"invalid database_id in ref: {exc.message}",
            location=text,
        ) from exc

    dm = _DIGEST_TAIL_RE.match(tail)
    if dm:
        return PackageRef(
            kind="digest",
            database_id=database_id,
            package_digest=f"sha256:{dm.group(1)}",
        )
    if not tail or "/" in tail and tail.startswith("sha256:"):
        raise ConfigError(
            "invalid_package",
            "invalid digest tail in package ref",
            location=text,
        )
    # version is opaque non-empty string (no @)
    if "@" in tail or not tail.strip():
        raise ConfigError(
            "invalid_package",
            "invalid version in package ref",
            location=text,
        )
    return PackageRef(kind="version", database_id=database_id, version=tail)
