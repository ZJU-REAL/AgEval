"""Independent evaluator: exchange + required tool workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKFLOW_PREFIX = ("find_customer", "get_order", "get_product", "request_exchange")


def _prefix_in_order(used: list[str]) -> bool:
    try:
        idxs = [used.index(step) for step in WORKFLOW_PREFIX]
    except ValueError:
        return False
    return idxs == sorted(idxs)


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(Path(inputs["artifacts"]["final-state"]).read_text(encoding="utf-8"))
    evaluation_dir = inputs.get("evaluation_dir")
    expected_path = (
        Path(str(evaluation_dir)) / "expected.json"
        if evaluation_dir
        else Path(__file__).resolve().parent / "evaluation" / "expected.json"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    used = (
        [str(x) for x in (data.get("tools_used") or [])]
        if isinstance(data.get("tools_used"), list)
        else []
    )
    order_ok = _prefix_in_order(used)
    # Deny trajectories that observed out-of-order successful attempts only via membership.
    denied = [
        o
        for o in (data.get("observations") or [])
        if isinstance(o, dict)
        and isinstance(o.get("result"), dict)
        and o["result"].get("error") == "workflow_order_denied"
    ]
    ok = (
        data.get("exchange_completed") is True
        and data.get("order_id") == expected.get("order_id")
        and list(data.get("from_item_ids") or []) == list(expected.get("from_item_ids") or [])
        and list(data.get("to_item_ids") or []) == list(expected.get("to_item_ids") or [])
        and order_ok
        and data.get("provider_session_handle") is None
        and bool(data.get("user_message"))
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "exchange_completed": data.get("exchange_completed"),
            "order_id": data.get("order_id"),
            "tools_used": used,
            "workflow_order_ok": order_ok,
            "order_denied_count": len(denied),
            "tool_calls": data.get("tool_calls"),
        },
    }
