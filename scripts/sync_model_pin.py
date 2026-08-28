#!/usr/bin/env python3
"""Pin models.dev (plus extra gateway prefixes) for Hub encyclopedia.

Maintainer/script only. Hub / Registry / CI request paths must not curl these
hosts. Run: python3 scripts/sync_model_pin.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIN_DIR = REPO / "apps/hub/src/lib/model-pin"
LOGO_DIR = REPO / "apps/hub/public/model-pin/logos"

MODELS_URL = "https://models.dev/models.json"
API_URL = "https://models.dev/api.json"
LAB_LOGO_URL = "https://models.dev/logos/labs/{lab}.svg"
LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# Gateways used in ageval overlays that are not models.dev provider ids.
EXTRA_PREFIXES = ("dashscope", "dashscope-", "litellm")

LAB_NAMES = {
    "aisingapore": "AI Singapore",
    "alibaba": "Alibaba",
    "anthropic": "Anthropic",
    "arcee-ai": "Arcee",
    "bytedance-seed": "ByteDance Seed",
    "cohere": "Cohere",
    "deepreinforce": "DeepReinforce",
    "deepseek": "DeepSeek",
    "google": "Google",
    "ibm": "IBM",
    "inclusionai": "InclusionAI",
    "meituan": "Meituan",
    "meta": "Meta",
    "microsoft": "Microsoft",
    "minimax": "MiniMax",
    "mistral": "Mistral",
    "moonshotai": "Moonshot",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "perplexity": "Perplexity",
    "poolside": "Poolside",
    "sakana": "Sakana",
    "sarvam": "Sarvam",
    "sdaia": "SDAIA",
    "stepfun": "StepFun",
    "swiss-ai": "Swiss AI",
    "tencent": "Tencent",
    "thinkingmachines": "Thinking Machines",
    "trendyol": "Trendyol",
    "upstage": "Upstage",
    "xai": "xAI",
    "xiaomi": "Xiaomi",
    "zhipuai": "Zhipu AI",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ageval-model-pin"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _add_lookup(lookup: dict[str, list[str]], key: str, canonical: str) -> None:
    text = (key or "").strip()
    if not text:
        return
    bucket = lookup.setdefault(text, [])
    if canonical not in bucket:
        bucket.append(canonical)


def _hf_weights(raw: object) -> str | None:
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if "huggingface.co/" in url:
            return url
    return None


def _map_provider_model(
    provider_id: str,
    model_id: str,
    canonicals: set[str],
    leaves: dict[str, list[str]],
) -> str | None:
    mid = (model_id or "").strip()
    if not mid:
        return None
    if mid.startswith("~"):
        mid = mid[1:]
    if ":" in mid:
        base, _tag = mid.rsplit(":", 1)
        if base in canonicals:
            return base
    if mid in canonicals:
        return mid
    prefixed = f"{provider_id}/{mid}"
    if prefixed in canonicals:
        return prefixed
    leaf = mid.rsplit("/", 1)[-1]
    hits = leaves.get(leaf) or []
    if len(hits) == 1:
        return hits[0]
    return None


def _litellm_price(row: object) -> dict[str, float] | None:
    if not isinstance(row, dict):
        return None
    inp = row.get("input_cost_per_token")
    out = row.get("output_cost_per_token")
    if not isinstance(inp, (int, float)) or not isinstance(out, (int, float)):
        return None
    return {"input": round(float(inp) * 1_000_000, 6), "output": round(float(out) * 1_000_000, 6)}


def build_pin(models: dict, api: dict, litellm: dict | None) -> dict:
    canonicals = {cid for cid in models if isinstance(cid, str) and "/" in cid}
    leaves: dict[str, list[str]] = {}
    for cid in sorted(canonicals):
        leaf = cid.rsplit("/", 1)[-1]
        leaves.setdefault(leaf, []).append(cid)

    labs: dict[str, dict[str, str]] = {}
    slim_models: dict[str, dict] = {}
    lookup: dict[str, list[str]] = {}
    prices: dict[str, dict[str, dict[str, float]]] = {}

    for cid in sorted(canonicals):
        row = models.get(cid) or {}
        if not isinstance(row, dict):
            continue
        lab = cid.split("/", 1)[0]
        labs[lab] = {
            "name": LAB_NAMES.get(lab, lab),
            "logo": f"{lab}.svg",
        }
        limit = row.get("limit") if isinstance(row.get("limit"), dict) else {}
        slim_models[cid] = {
            "name": str(row.get("name") or cid.rsplit("/", 1)[-1]),
            "description": str(row.get("description") or ""),
            "family": str(row.get("family") or ""),
            "lab": lab,
            "release_date": str(row.get("release_date") or ""),
            "context": limit.get("context"),
            "output": limit.get("output"),
            "open_weights": bool(row.get("open_weights")),
            "reasoning": bool(row.get("reasoning")),
            "tool_call": bool(row.get("tool_call")),
            "attachment": bool(row.get("attachment")),
            "weights": _hf_weights(row.get("weights")),
        }
        _add_lookup(lookup, cid, cid)
        _add_lookup(lookup, cid.rsplit("/", 1)[-1], cid)

    prefixes = set(EXTRA_PREFIXES)
    for provider_id, provider in api.items():
        if not isinstance(provider_id, str) or not isinstance(provider, dict):
            continue
        prefixes.add(provider_id)
        for mid, mrow in (provider.get("models") or {}).items():
            if not isinstance(mid, str):
                continue
            canonical = _map_provider_model(provider_id, mid, canonicals, leaves)
            if canonical is None:
                continue
            _add_lookup(lookup, mid, canonical)
            cost = mrow.get("cost") if isinstance(mrow, dict) else None
            if isinstance(cost, dict) and isinstance(cost.get("input"), (int, float)):
                bucket = prices.setdefault(canonical, {})
                bucket[provider_id] = {
                    "input": float(cost["input"]),
                    "output": float(cost["output"]) if isinstance(cost.get("output"), (int, float)) else 0.0,
                }

    if isinstance(litellm, dict):
        for key, row in litellm.items():
            if not isinstance(key, str) or key.startswith("sample_"):
                continue
            canonical = key if key in canonicals else None
            if canonical is None:
                hits = lookup.get(key) or []
                if len(hits) == 1:
                    canonical = hits[0]
            if canonical is None:
                continue
            if prices.get(canonical):
                continue
            litellm_cost = _litellm_price(row)
            if litellm_cost is None:
                continue
            prices[canonical] = {"litellm": litellm_cost}

    prefix_list = sorted(prefixes, key=lambda p: (-len(p), p))
    return {
        "format": "ageval.model-pin/1",
        "source": "models.dev",
        "pinned_at": date.today().isoformat(),
        "labs": {k: labs[k] for k in sorted(labs)},
        "models": slim_models,
        "prefixes": prefix_list,
        "lookup": {k: lookup[k] for k in sorted(lookup)},
        "prices": {k: prices[k] for k in sorted(prices)},
        "aliases": {},
    }


def write_logos(labs: list[str]) -> None:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    for lab in labs:
        dest = LOGO_DIR / f"{lab}.svg"
        try:
            dest.write_bytes(_get(LAB_LOGO_URL.format(lab=lab)))
        except Exception:
            continue


def main() -> int:
    models = json.loads(_get(MODELS_URL).decode("utf-8"))
    api = json.loads(_get(API_URL).decode("utf-8"))
    if not isinstance(models, dict) or not isinstance(api, dict):
        raise SystemExit("models.dev payload is not an object")
    litellm: dict | None = None
    try:
        litellm = json.loads(_get(LITELLM_URL).decode("utf-8"))
    except Exception:
        litellm = None
    pin = build_pin(models, api, litellm)
    PIN_DIR.mkdir(parents=True, exist_ok=True)
    (PIN_DIR / "pin.json").write_text(
        json.dumps(pin, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_logos(list(pin["labs"]))
    print(
        f"pinned {len(pin['models'])} models, {len(pin['labs'])} labs, "
        f"{len(pin['lookup'])} lookup keys → {PIN_DIR / 'pin.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
