"""Job-binding helpers for tests (extension-row options, no profile bag)."""

from __future__ import annotations

from typing import Any


def acp_extensions(entry: str, **extra: Any) -> list[dict[str, Any]]:
    opts: dict[str, Any] = {"entry": entry, **extra}
    return [{"plugin": "acp", "options": opts}]


def plugin_extensions(plugin: str, **options: Any) -> list[dict[str, Any]]:
    row: dict[str, Any] = {"plugin": plugin}
    if options:
        row["options"] = dict(options)
    return [row]


def acp_binding(entry: str, **fields: Any) -> dict[str, Any]:
    row = {"executor": "acp", "extensions": acp_extensions(entry)}
    row.update(fields)
    return row
