"""Binding ``overlays`` — published Database file set (paths only).

Config owns this list. Plugin ``options.src`` is never read to build or
check it. Listed files must stay secret-free (locators only).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from bora.config.errors import (
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_MISSING_REFERENCE,
    ERROR_PATH_OUTSIDE_PACKAGE,
    ConfigError,
)

OVERLAYS_PREFIX = "overlays/"
_MAX_SCAN_BYTES = 1_000_000

_LOCATOR_RE = re.compile(
    r"\{env:[A-Za-z_][A-Za-z0-9_]*\}"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*\}"
    r"|\$[A-Za-z_][A-Za-z0-9_]*"
)
_PEM_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----")
_TOKEN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{16,}=*"),
    re.compile(r"(?i)xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9\-_]{20,}"),
)
_ASSIGN_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|passwd|credential)\s*[:=]\s*[\"']?([^\s\"']+)"
)
_ENTROPY_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")
_ENTROPY_MIN_LEN = 32
_ENTROPY_MIN = 4.5


def parse_overlay_paths(raw: Any, *, location: str) -> list[str]:
    """Validate the ``overlays`` list shape and return normalized paths."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "overlays must be a list of non-empty strings",
            location=location,
        )
    out: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        path = normalize_overlay_path(item, location=f"{location}/{idx}")
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def normalize_overlay_path(raw: Any, *, location: str) -> str:
    """Database-relative path that must start with ``overlays/``."""
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "overlay path must be a non-empty string",
            location=location,
        )
    text = raw.strip().replace("\\", "/")
    if text.startswith("~"):
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            "overlay path must not use host ~",
            location=location,
        )
    if text.startswith("/") or Path(text).is_absolute():
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            "overlay path must be Database-relative",
            location=location,
        )
    raw_parts = text.split("/")
    if any(part == "" for part in raw_parts):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "overlay path must not contain empty segments",
            location=location,
        )
    parts = [part for part in raw_parts if part != "."]
    if not parts or ".." in parts:
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            "overlay path must not escape the Database root",
            location=location,
        )
    if parts[0] != "overlays" or len(parts) < 2:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "overlay path must start with overlays/",
            location=location,
        )
    return "/".join(parts)


def overlay_paths_from_binding(binding: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(binding, Mapping) or "overlays" not in binding:
        return []
    return parse_overlay_paths(
        binding.get("overlays"),
        location="overlays",
    )


def resolve_overlay_target(database_root: Path, rel: str, *, location: str) -> Path:
    """Resolve *rel* under the Database root; fail if missing or escaping."""
    root = database_root.expanduser().resolve(strict=False)
    target = (root / rel).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            f"overlay path escapes Database root: {rel}",
            location=location,
        ) from exc
    if not target.exists():
        raise ConfigError(
            ERROR_MISSING_REFERENCE,
            f"overlay path not found: {rel}",
            location=location,
        )
    return target


def iter_overlay_files(database_root: Path, paths: Sequence[str], *, location: str) -> list[Path]:
    """Expand declared files/dirs to regular files (recursive)."""
    files: list[Path] = []
    seen: set[Path] = set()
    for rel in paths:
        target = resolve_overlay_target(database_root, rel, location=location)
        if target.is_dir():
            for child in sorted(target.rglob("*")):
                if not child.is_file():
                    continue
                resolved = child.resolve(strict=False)
                try:
                    resolved.relative_to(database_root.expanduser().resolve(strict=False))
                except ValueError as exc:
                    raise ConfigError(
                        ERROR_PATH_OUTSIDE_PACKAGE,
                        f"overlay path escapes Database root: {rel}",
                        location=location,
                    ) from exc
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
        elif target.is_file():
            if target not in seen:
                seen.add(target)
                files.append(target)
        else:
            raise ConfigError(
                ERROR_MISSING_REFERENCE,
                f"overlay path is not a file or directory: {rel}",
                location=location,
            )
    return files


def overlay_secret_hits(text: str) -> list[str]:
    """Class labels of residual secrets after locator masking. Empty = clean."""
    masked = _LOCATOR_RE.sub("LOCATOR", text)
    hits: list[str] = []
    if _PEM_RE.search(masked):
        hits.append("pem")
    for pat in _TOKEN_RES:
        if pat.search(masked):
            hits.append("token")
            break
    for match in _ASSIGN_RE.finditer(masked):
        value = match.group(1)
        if _value_is_secret(value):
            hits.append("assignment")
            break
    if _high_entropy_hit(masked):
        hits.append("entropy")
    return hits


def scan_overlay_files(files: Iterable[Path], *, location: str) -> None:
    """Fail closed when a listed overlay file embeds secret material."""
    for path in files:
        try:
            raw = path.read_bytes()[:_MAX_SCAN_BYTES]
        except OSError as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot read overlay file: {path.name}",
                location=location,
            ) from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="ignore")
            if not _PEM_RE.search(text):
                continue
        hits = overlay_secret_hits(text)
        if hits:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "overlay file contains secret material (use locators only)",
                location=location,
            )


def assert_job_overlay_files(
    database_root: Path,
    overlay: Mapping[str, Any] | None,
) -> None:
    """Scan ``job_overlay.bindings.*.overlays`` before upload-suite."""
    if not isinstance(overlay, Mapping):
        return
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping):
        return
    for role_id, raw in bindings.items():
        if not isinstance(raw, Mapping):
            continue
        rid = str(role_id).strip() or str(role_id)
        assert_overlays_at_lock(
            database_root,
            raw,
            location=f"/job_overlay/bindings/{rid}/overlays",
        )


def assert_overlays_at_lock(
    database_root: Path | None,
    binding: Mapping[str, Any],
    *,
    location: str,
) -> None:
    """Syntax + existence + secret scan. No-op when the field is omitted or []."""
    if "overlays" not in binding:
        return
    paths = parse_overlay_paths(binding.get("overlays"), location=location)
    if not paths:
        return
    if database_root is None:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "overlays require a Database root",
            location=location,
        )
    files = iter_overlay_files(database_root, paths, location=location)
    scan_overlay_files(files, location=location)


def _value_is_secret(value: str) -> bool:
    if not value or value == "LOCATOR":
        return False
    if value.lower() in {"true", "false", "null", "none", "undefined"}:
        return False
    if _PEM_RE.search(value):
        return True
    for pat in _TOKEN_RES:
        if pat.search(value):
            return True
    return len(value) >= _ENTROPY_MIN_LEN and _shannon(value) >= _ENTROPY_MIN


def _high_entropy_hit(text: str) -> bool:
    for token in _ENTROPY_TOKEN_RE.findall(text):
        if token == "LOCATOR" or len(token) < _ENTROPY_MIN_LEN:
            continue
        if _shannon(token) >= _ENTROPY_MIN:
            return True
    return False


def _shannon(token: str) -> float:
    counts: dict[str, int] = {}
    for ch in token:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(token)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())
