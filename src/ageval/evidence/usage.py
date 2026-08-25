"""Sealed ``terminal.usage`` (first-class token/cost) and sibling ``extra``.

Observational — never PASS. Unknown first-class quantities are omitted;
do not invent zeros that imply a measurement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FIRST_CLASS_KEYS = frozenset({"prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd"})


def sealed_usage(
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cached_tokens: int | None = None,
    cost_usd: float | int | None = None,
) -> dict[str, Any] | None:
    """Build layer-C first-class usage. No extra bag."""
    out: dict[str, Any] = {}
    if prompt_tokens is not None:
        out["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        out["completion_tokens"] = completion_tokens
    if cached_tokens is not None:
        out["cached_tokens"] = cached_tokens
    if cost_usd is not None:
        out["cost_usd"] = cost_usd
    return out or None


def sealed_extra(extra: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Vendor/plugin bag for the terminal row sibling ``extra``. Empty omitted."""
    if not extra:
        return None
    out: dict[str, Any] = {}
    for key, value in extra.items():
        if key in FIRST_CLASS_KEYS:
            continue
        out[key] = value
    return out or None
