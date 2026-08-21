"""Canonical JSON + digest helpers for Config Core locks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ageval.config.errors import ERROR_PATH_OUTSIDE_PACKAGE, ConfigError


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """UTF-8 canonical JSON: sorted object keys, arrays preserve order, no whitespace."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_payload(payload: Mapping[str, Any]) -> str:
    """Return ``sha256:<64 lowercase hex>`` over the canonical payload."""
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


def normalize_package_relpath(path: str) -> str:
    """Normalize a package-relative path for stable digests (posix, no host abs)."""
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/") or p.startswith("..") or "/../" in f"/{p}/":
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            f"path not package-relative: {path}",
            location=path,
        )
    return p
