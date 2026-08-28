"""Hub overlay → canonical join. Keep in lockstep with apps/hub/src/lib/model-pin/join.ts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PIN_PATH = REPO / "apps/hub/src/lib/model-pin/pin.json"


def load_pin() -> dict[str, Any]:
    if not PIN_PATH.is_file():
        return {
            "format": "ageval.model-pin/1",
            "labs": {},
            "models": {},
            "prefixes": [],
            "lookup": {},
            "prices": {},
            "aliases": {},
        }
    raw = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format") != "ageval.model-pin/1":
        return {
            "format": "ageval.model-pin/1",
            "labs": {},
            "models": {},
            "prefixes": [],
            "lookup": {},
            "prices": {},
            "aliases": {},
        }
    return raw


def peel_prefix(value: str, prefixes: list[str]) -> str | None:
    for prefix in prefixes:
        if not prefix:
            continue
        if prefix.endswith("-"):
            if value.startswith(prefix) and len(value) > len(prefix):
                return value[len(prefix) :]
            continue
        token = f"{prefix}/"
        if value.startswith(token):
            return value[len(token) :]
    return None


def overlay_candidates(overlay: str, prefixes: list[str]) -> list[str]:
    text = overlay.strip()
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        next_ = value.strip().strip("/")
        if not next_ or next_ in seen:
            return
        seen.add(next_)
        out.append(next_)

    add(text)
    once = peel_prefix(text, prefixes)
    if once:
        add(once)
        twice = peel_prefix(once, prefixes)
        if twice:
            add(twice)
    parts = [p for p in text.split("/") if p]
    if parts:
        add(parts[-1])
    if len(parts) >= 2:
        add("/".join(parts[-2:]))
    return out


def join_overlay(overlay: str, pin: dict[str, Any] | None) -> dict[str, Any]:
    text = overlay.strip()
    if not text or not pin:
        return {"overlay": text, "canonical": None, "hits": []}
    alias = str((pin.get("aliases") or {}).get(text) or "").strip()
    models = pin.get("models") or {}
    if alias and alias in models:
        return {"overlay": text, "canonical": alias, "hits": [alias]}
    hits: set[str] = set()
    lookup = pin.get("lookup") or {}
    for candidate in overlay_candidates(text, list(pin.get("prefixes") or [])):
        ids = lookup.get(candidate) or []
        for item in ids:
            if item in models:
                hits.add(item)
    unique = sorted(hits)
    return {
        "overlay": text,
        "canonical": unique[0] if len(unique) == 1 else None,
        "hits": unique,
    }
