"""Usage / cache / latency formatting for viewer trial meta (observational)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_terminal_usage(traj_path: Path) -> dict[str, Any] | None:
    """Last terminal.usage object from a trajectory.jsonl (fail-open)."""
    if not traj_path.is_file():
        return None
    last: dict[str, Any] | None = None
    try:
        with traj_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "terminal":
                    continue
                usage = obj.get("usage")
                if isinstance(usage, dict) and usage:
                    last = usage
    except OSError:
        return None
    return last


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val == int(val):
        return int(val)
    return None


def _cache_hit_heuristic(
    *,
    input_tokens: int | None,
    cached_read_tokens: int | None,
    total_tokens: int | None = None,
    cached_write_tokens: int | None = None,
) -> dict[str, Any]:
    """Infer cache relation + hit rate from ACP Usage numbers (#30/#27).

    ACP does **not** fix whether ``cachedReadTokens ⊆ inputTokens``. Entries map
    vendor APIs differently (OpenAI-style inclusion vs Anthropic-style disjoint).
    Heuristic only — not PASS authority, not protocol law.

    - **inclusion** (``0 < cache ≤ input``): hit = cache / input;
      display total input stays ``input``.
    - **disjoint** (``cache > input``): hit = cache / (input + cache [+ write]);
      display total input = that denominator.
    - Prefer ``total_tokens`` as a weak corroboration when both models are
      plausible (not used to invent a third model).
    - Missing/zero cache → no rate.
    """
    empty: dict[str, Any] = {
        "cache_relation": None,
        "cache_hit_rate": None,
        "display_input_tokens": input_tokens,
    }
    if input_tokens is None or cached_read_tokens is None:
        return empty
    if input_tokens < 0 or cached_read_tokens < 0:
        return empty
    if cached_read_tokens == 0:
        # Explicit zero cache: rate 0% only when we have positive input.
        if input_tokens > 0:
            return {
                "cache_relation": "inclusion",
                "cache_hit_rate": 0.0,
                "display_input_tokens": input_tokens,
            }
        return empty

    write = (
        cached_write_tokens
        if isinstance(cached_write_tokens, int) and cached_write_tokens > 0
        else 0
    )

    # Size-based primary split.
    if cached_read_tokens <= input_tokens and input_tokens > 0:
        relation = "inclusion"
        # Weak total check: if total ≈ input+cache, prefer disjoint anyway.
        if (
            total_tokens is not None
            and total_tokens > 0
            and abs(total_tokens - (input_tokens + cached_read_tokens))
            <= max(8, int(0.02 * total_tokens))
            and abs(total_tokens - input_tokens) > max(8, int(0.02 * total_tokens))
        ):
            relation = "disjoint"
    else:
        # cache > input (or input == 0 with positive cache)
        relation = "disjoint"

    if relation == "inclusion":
        rate = cached_read_tokens / input_tokens if input_tokens > 0 else None
        return {
            "cache_relation": "inclusion",
            "cache_hit_rate": rate,
            "display_input_tokens": input_tokens,
        }

    # disjoint: Anthropic-style parallel buckets
    denom = input_tokens + cached_read_tokens + write
    if denom <= 0:
        return empty
    rate = cached_read_tokens / denom
    return {
        "cache_relation": "disjoint",
        "cache_hit_rate": rate,
        "display_input_tokens": denom,
    }


def _usage_summary_for_actor(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a terminal usage dict into viewer-facing summary fields (#27/#30).

    - Prefer normalized keys (input_tokens / output_tokens / cost / context).
    - Never treat legacy ``used`` (context occupancy) as tokens.
    - Cache hit rate via :func:`_cache_hit_heuristic` (inclusion vs disjoint).
    - Observational only; not PASS authority.
    """
    if not isinstance(usage, dict) or not usage:
        return None

    inp = _as_int(
        usage.get("input_tokens") if "input_tokens" in usage else usage.get("inputTokens")
    )
    outp = _as_int(
        usage.get("output_tokens") if "output_tokens" in usage else usage.get("outputTokens")
    )
    cached_read = _as_int(
        usage.get("cached_read_tokens")
        if "cached_read_tokens" in usage
        else usage.get("cachedReadTokens")
    )
    cached_write = _as_int(
        usage.get("cached_write_tokens")
        if "cached_write_tokens" in usage
        else usage.get("cachedWriteTokens")
    )
    total = _as_int(
        usage.get("total_tokens") if "total_tokens" in usage else usage.get("totalTokens")
    )

    cost_raw = usage.get("cost")
    cost_amount: float | int | None = None
    cost_currency: str | None = None
    if isinstance(cost_raw, dict):
        amt = cost_raw.get("amount")
        if isinstance(amt, (int, float)) and not isinstance(amt, bool):
            cost_amount = amt
        cur = cost_raw.get("currency")
        if isinstance(cur, str) and cur.strip():
            cost_currency = cur.strip()
    # Legacy flat cost is rare; ignore non-mapping.

    context_raw = usage.get("context") if isinstance(usage.get("context"), dict) else None
    context_used = _as_int(context_raw.get("used")) if isinstance(context_raw, dict) else None
    context_size = _as_int(context_raw.get("size")) if isinstance(context_raw, dict) else None
    # Old evidence: top-level used/size only — keep as context, never as tokens.
    if context_used is None:
        context_used = _as_int(usage.get("used"))
    if context_size is None:
        context_size = _as_int(usage.get("size"))

    cache_info = _cache_hit_heuristic(
        input_tokens=inp,
        cached_read_tokens=cached_read,
        total_tokens=total,
        cached_write_tokens=cached_write,
    )
    cache_hit_rate = cache_info.get("cache_hit_rate")
    cache_relation = cache_info.get("cache_relation")
    display_input = cache_info.get("display_input_tokens")
    if not isinstance(display_input, int):
        display_input = inp

    has_tokens = inp is not None or outp is not None
    has_cost = cost_amount is not None
    has_context = context_used is not None or context_size is not None
    if not has_tokens and not has_cost and not has_context:
        return None

    summary: dict[str, Any] = {
        "input_tokens": inp,
        "output_tokens": outp,
        "total_tokens": total,
        "cached_read_tokens": cached_read,
        "cached_write_tokens": cached_write,
        "cache_hit_rate": cache_hit_rate,
        "cache_relation": cache_relation,
        "display_input_tokens": display_input,
        "cost_amount": cost_amount,
        "cost_currency": cost_currency,
        "context_used": context_used,
        "context_size": context_size,
        # Human label assembled server-side so SPA stays thin; observational.
        "label": _format_usage_label(
            input_tokens=display_input,
            output_tokens=outp,
            cache_hit_rate=cache_hit_rate if isinstance(cache_hit_rate, float) else None,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
        ),
    }
    return summary


def _format_usage_label(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_hit_rate: float | None,
    cost_amount: float | int | None,
    cost_currency: str | None,
) -> str | None:
    """Compact Usage column text, e.g. ``in 11.4K / out 140 · cache 75% · $0.012``.

    ``input_tokens`` here is the **display** total (inclusion: raw input;
    disjoint: input + cached_read [+ write]).
    """
    parts: list[str] = []
    if input_tokens is not None or output_tokens is not None:
        in_s = _fmt_token_count(input_tokens) if input_tokens is not None else "-"
        out_s = _fmt_token_count(output_tokens) if output_tokens is not None else "-"
        parts.append(f"in {in_s} / out {out_s}")
    if cache_hit_rate is not None:
        pct = max(0.0, min(1.0, float(cache_hit_rate))) * 100.0
        parts.append(f"cache {pct:.0f}%")
    if cost_amount is not None:
        cur = (cost_currency or "").upper()
        if cur in {"", "USD"}:
            parts.append(f"${_fmt_cost(cost_amount)}")
        else:
            parts.append(f"{_fmt_cost(cost_amount)} {cur}")
    if not parts:
        return None
    return " · ".join(parts)


def _fmt_token_count(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    if n >= 1000:
        v = n / 1000
        return f"{int(v)}K" if v == int(v) else f"{v:.1f}K"
    return str(n)


def _fmt_cost(amount: float | int) -> str:
    if isinstance(amount, int) or float(amount) == int(amount):
        if float(amount) == 0:
            return "0"
        return f"{float(amount):.4g}"
    # Prefer up to 4 significant decimals for small USD amounts.
    return f"{float(amount):.4g}"


def _format_latency_ms(total_ms: float | None, invokes: int) -> str | None:
    if total_ms is None:
        return None
    seconds = total_ms / 1000.0
    if seconds >= 10:
        body = f"{seconds:.0f}s"
    elif seconds >= 1:
        body = f"{seconds:.1f}s".replace(".0s", "s")
    else:
        body = f"{total_ms:.0f}ms"
    if invokes > 0:
        return f"{body} ({invokes})"
    return body
