"""Builtin harness short ids: catalog overlay, not Hub uploads (design/14)."""

from __future__ import annotations

import json
from pathlib import Path

from ageval.config.errors import ERROR_INVALID_PACKAGE, ConfigError

_CATALOG = Path(__file__).resolve().parent / "builtin" / "catalog.json"
_ROW_KEYS = frozenset({"harness_id", "kind", "product", "label", "description"})


def _load_rows() -> tuple[dict[str, str], ...]:
    raw = json.loads(_CATALOG.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "builtin agent catalog is empty",
            location=str(_CATALOG),
        )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != _ROW_KEYS:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "builtin agent row keys: harness_id, kind, product, label, description",
                location=str(_CATALOG),
            )
        harness_id = str(item["harness_id"]).strip()
        if not harness_id or "/" in harness_id or harness_id in seen:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"invalid builtin harness_id {harness_id!r}",
                location=str(_CATALOG),
            )
        seen.add(harness_id)
        rows.append(
            {
                "harness_id": harness_id,
                "kind": str(item["kind"]).strip(),
                "product": str(item["product"]).strip(),
                "label": str(item["label"]).strip(),
                "description": str(item["description"]).strip(),
            }
        )
    return tuple(rows)


_ROWS: tuple[dict[str, str], ...] | None = None


def builtin_harness_rows() -> tuple[dict[str, str], ...]:
    global _ROWS
    if _ROWS is None:
        _ROWS = _load_rows()
    return _ROWS


def builtin_harness_ids() -> frozenset[str]:
    return frozenset(row["harness_id"] for row in builtin_harness_rows())


def _locator(raw: str) -> str:
    return raw.strip().split("@", 1)[0].strip()


def _match_id(leaf: str) -> str | None:
    key = leaf.casefold()
    if not key:
        return None
    for row in builtin_harness_rows():
        if row["harness_id"].casefold() == key:
            return row["harness_id"]
    return None


def canonical_harness_id(raw: str) -> str | None:
    """Short catalog id only. ``org/name`` is never the overlay route."""
    locator = _locator(raw)
    if not locator or "/" in locator:
        return None
    return _match_id(locator)


def reserved_harness_leaf(raw: str) -> str | None:
    """Reserved short id if *raw* is one, or aliases one as ``org/<id>``."""
    locator = _locator(raw)
    if not locator:
        return None
    return _match_id(locator.rsplit("/", 1)[-1])


def builtin_harness_root(harness_id: str) -> Path:
    canonical = canonical_harness_id(harness_id)
    if canonical is None:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"unknown builtin harness {harness_id!r}",
            location=str(_CATALOG),
        )
    return Path(__file__).resolve().parent / "builtin" / canonical


def reject_reserved_harness_id(agent_id: str) -> None:
    hit = reserved_harness_leaf(agent_id)
    if hit is None:
        return
    raise ConfigError(
        ERROR_INVALID_PACKAGE,
        f"{hit} ships with ageval; it is not a Hub package",
        location="agent.yaml:/agent_id",
    )
