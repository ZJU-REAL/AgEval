"""Sealed ``terminal.usage``: first-class token/cost fields plus extra bag.

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
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a layer-C usage object.

    ``extra`` is the vendor/plugin bag. First-class names passed through
    ``extra`` are dropped from the bag (they belong on the object itself).
    Empty extra is omitted. Returns ``None`` when nothing was reported.
    """
    out: dict[str, Any] = {}
    if prompt_tokens is not None:
        out["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        out["completion_tokens"] = completion_tokens
    if cached_tokens is not None:
        out["cached_tokens"] = cached_tokens
    if cost_usd is not None:
        out["cost_usd"] = cost_usd
    extra_out: dict[str, Any] = {}
    if extra:
        for key, value in extra.items():
            if key in FIRST_CLASS_KEYS:
                continue
            extra_out[key] = value
    if extra_out:
        out["extra"] = extra_out
    return out or None
