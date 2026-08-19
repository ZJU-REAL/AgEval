from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Evaluator-only truth (WebShop-style graded reward).
REQUIRED_ATTRS: list[str] = ['wireless', 'over-ear']
REQUIRED_OPTIONS: dict[str, str] = {'color': 'black'}
PRICE_CAP: float = 50.0


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["purchase"]).read_text(encoding="utf-8"))
    purchase = data.get("purchase")
    total = len(REQUIRED_ATTRS) + len(REQUIRED_OPTIONS) + 1  # +1 = price constraint
    if not isinstance(purchase, dict):
        return {"status": "FAIL", "score": 0.0,
                "metrics": {"bought": False, "n_steps": data.get("n_steps")}}
    attrs = {a.lower() for a in purchase.get("attributes") or []}
    opts = {str(k).lower(): str(v).lower() for k, v in (purchase.get("options") or {}).items()}
    matched = sum(1 for a in REQUIRED_ATTRS if a.lower() in attrs)
    matched += sum(1 for k, v in REQUIRED_OPTIONS.items() if opts.get(k.lower()) == v.lower())
    price = float(purchase.get("price") or 0.0)
    price_ok = price <= PRICE_CAP
    matched += 1 if price_ok else 0
    reward = matched / total
    return {
        "status": "PASS" if reward == 1.0 else "FAIL",
        "score": round(reward, 4),
        "metrics": {
            "bought": True, "item_id": purchase.get("item_id"),
            "price": price, "price_ok": price_ok,
            "matched": matched, "required": total,
            "options_chosen": purchase.get("options"),
            "n_steps": data.get("n_steps"),
        },
    }
