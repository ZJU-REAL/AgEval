"""Map Chat Completions ``usage`` onto sealed first-class fields + extra.

Observational — never PASS. Missing backend usage stays omitted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ageval.evidence.usage import sealed_extra, sealed_usage

_USAGE_RESERVED = frozenset(
    {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
        "input_tokens",
        "output_tokens",
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


def _pick_int(data: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in data:
            continue
        found = _as_int(data[key])
        if found is not None:
            return found
    return None


def normalize_openai_http_usage(
    raw: Any,
    *,
    response_id: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Fold a Chat Completions ``usage`` object (and optional response ``id``).

    Returns ``(usage, extra)``. First-class usage is token/cost fields.
    Leftovers (``reasoning_tokens``, cache-write, raw ``id``, ``total_tokens``)
    land in sibling extra. Does not invent zeros for omitted keys.
    """
    if not isinstance(raw, dict) or not raw:
        if isinstance(response_id, str) and response_id.strip():
            return None, sealed_extra({"id": response_id.strip()})
        return None, None

    extra: dict[str, Any] = {}
    prompt_tokens = _pick_int(raw, "prompt_tokens", "input_tokens")
    completion_tokens = _pick_int(raw, "completion_tokens", "output_tokens", "text_tokens")
    cached_tokens = _pick_int(raw, "cached_tokens")

    prompt_details = raw.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        if cached_tokens is None:
            cached_tokens = _as_int(prompt_details.get("cached_tokens"))
        for key, value in prompt_details.items():
            if key == "cached_tokens":
                continue
            dest = key if key not in extra else f"prompt_{key}"
            extra[dest] = value

    completion_details = raw.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        if "reasoning_tokens" in completion_details:
            extra["reasoning_tokens"] = completion_details["reasoning_tokens"]
        text_tokens = _as_int(completion_details.get("text_tokens"))
        if completion_tokens is None and text_tokens is not None:
            completion_tokens = text_tokens
        for key, value in completion_details.items():
            if key == "reasoning_tokens":
                continue
            dest = key if key not in extra else f"completion_{key}"
            extra[dest] = value

    total = _pick_int(raw, "total_tokens")
    if total is not None:
        extra["total_tokens"] = total

    cost_usd: float | int | None = None
    if "cost_usd" in raw:
        cost_usd = _as_number(raw.get("cost_usd"))
    cost_raw = raw.get("cost")
    if cost_usd is None and isinstance(cost_raw, int | float) and not isinstance(cost_raw, bool):
        cost_usd = _as_number(cost_raw)
    elif isinstance(cost_raw, dict):
        amount = _as_number(cost_raw.get("amount"))
        currency = cost_raw.get("currency")
        cur = currency.strip().upper() if isinstance(currency, str) else ""
        if amount is not None and cur in {"", "USD"}:
            cost_usd = amount
        else:
            extra["cost"] = dict(cost_raw)

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
