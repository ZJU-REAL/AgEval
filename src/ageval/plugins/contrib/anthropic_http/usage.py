"""Map Anthropic Messages ``usage`` onto sealed first-class fields + extra.

Observational — never PASS. Missing backend usage stays omitted.
"""

from __future__ import annotations

import math
from typing import Any

from ageval.evidence.usage import sealed_extra, sealed_usage

_USAGE_RESERVED = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "cost",
        "cost_usd",
    }
)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value) or value != int(value):
        return None
    return int(value)


def _as_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    return value


def normalize_anthropic_http_usage(
    raw: Any,
    *,
    response_id: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Fold a Messages ``usage`` object (and optional response ``id``)."""
    if not isinstance(raw, dict) or not raw:
        if isinstance(response_id, str) and response_id.strip():
            return None, sealed_extra({"id": response_id.strip()})
        return None, None

    extra: dict[str, Any] = {}
    prompt_tokens = _as_int(raw.get("input_tokens"))
    if prompt_tokens is None:
        prompt_tokens = _as_int(raw.get("prompt_tokens"))
    completion_tokens = _as_int(raw.get("output_tokens"))
    if completion_tokens is None:
        completion_tokens = _as_int(raw.get("completion_tokens"))
    cached_tokens = _as_int(raw.get("cache_read_input_tokens"))
    if cached_tokens is None:
        cached_tokens = _as_int(raw.get("cached_tokens"))

    cost_usd: float | int | None = None
    if "cost_usd" in raw:
        cost_usd = _as_number(raw.get("cost_usd"))
    elif "cost" in raw:
        cost_usd = _as_number(raw.get("cost"))

    if isinstance(response_id, str) and response_id.strip():
        extra["id"] = response_id.strip()

    for key, value in raw.items():
        if key in _USAGE_RESERVED:
            continue
        extra.setdefault(key, value)

    return (
        sealed_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
        ),
        sealed_extra(extra or None),
    )
