"""Allowlisted CLI --set JSON Pointer overrides."""

from __future__ import annotations

import json
from typing import Any

from bora.config.constants import ALLOWLISTED_OVERRIDE_POINTERS
from bora.config.errors import ERROR_INVALID_OVERRIDE, ConfigError
from bora.config.profiles import is_binding_override_pointer


def is_allowlisted_override_pointer(pointer: str) -> bool:
    """True for fixed parameter pointers or ``/bindings/<role>/…`` axes (#59)."""
    if pointer in ALLOWLISTED_OVERRIDE_POINTERS:
        return True
    return is_binding_override_pointer(pointer)


def parse_set_override(raw: str) -> tuple[str, Any]:
    """Parse ``<JSON Pointer>=<JSON value>`` into a pointer and decoded value."""
    if "=" not in raw:
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "override must be <JSON Pointer>=<JSON value>",
            location=raw,
        )
    pointer, _, value_text = raw.partition("=")
    if not pointer.startswith("/"):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "JSON Pointer must start with /",
            location=pointer,
        )
    if not is_allowlisted_override_pointer(pointer):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"pointer not allowlisted for override: {pointer}",
            location=pointer,
        )
    try:
        value = json.loads(value_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"override value is not valid JSON: {value_text!r}",
            location=pointer,
        ) from exc
    return pointer, value


def apply_json_pointer(doc: dict[str, Any], pointer: str, value: Any) -> None:
    """Set an allowlisted leaf via JSON Pointer (no document-root structural replace)."""
    if pointer == "" or pointer == "/":
        raise ConfigError(ERROR_INVALID_OVERRIDE, "cannot replace document root", location=pointer)
    parts = [p for p in pointer.split("/") if p != ""]
    # Unescape JSON Pointer tokens (~1 → /, ~0 → ~).
    tokens = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    cursor: Any = doc
    for token in tokens[:-1]:
        if not isinstance(cursor, dict) or token not in cursor:
            raise ConfigError(
                ERROR_INVALID_OVERRIDE,
                f"override path missing intermediate key: {token}",
                location=pointer,
            )
        cursor = cursor[token]
        if not isinstance(cursor, dict):
            raise ConfigError(
                ERROR_INVALID_OVERRIDE,
                "cannot descend into non-object for override",
                location=pointer,
            )
    leaf = tokens[-1]
    if not isinstance(cursor, dict):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE, "override target parent is not an object", location=pointer
        )
    if leaf not in cursor:
        # Allow setting known leaves that defaults may have created; reject unknown structure.
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"override target key does not exist: {leaf}",
            location=pointer,
        )
    # Refuse replacing entire objects/arrays via allowlisted leaf pointers with wrong types
    # only when the existing value is a mapping and new value tries full structure swap of roots.
    existing = cursor[leaf]
    if isinstance(existing, dict) and not isinstance(value, dict):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "cannot replace object with non-object via override",
            location=pointer,
        )
    cursor[leaf] = value
