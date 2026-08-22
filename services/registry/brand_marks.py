"""Closed marketplace icon_key allowlist (design/12)."""

from __future__ import annotations

import json
from pathlib import Path

from services.registry.errors import RegistryAppError

_PATH = Path(__file__).with_name("brand_marks.json")
ALLOWED_KEYS: frozenset[str] = frozenset(
    json.loads(_PATH.read_text(encoding="utf-8")),
)


def normalize_icon_key(raw: object) -> str:
    """Return a catalog key, or empty string to clear. Unknown keys fail closed."""
    if not isinstance(raw, str):
        raise RegistryAppError("invalid_request", "unknown icon_key", http_status=400)
    key = raw.strip().lower()
    if not key:
        return ""
    if key not in ALLOWED_KEYS:
        raise RegistryAppError("invalid_request", "unknown icon_key", http_status=400)
    return key
