"""Retail domain tools and package state helpers (not orchestration)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ageval_sdk import Tool, ToolSet

WORKFLOW_PREFIX = (
    "find_customer",
    "get_order",
    "get_product",
    "request_exchange",
)

TOOL_CATALOG = """
Tools (results only via harness execution — never invent observations):
- find_customer(email)
- get_order(order_id)  # ids may look like #W....; result includes line_items + product_catalog
- get_product(item_id)  # also returns other_products for variants
- request_exchange(order_id, from_item_ids, to_item_ids)
- done(note?)
Harness enforces order: find_customer → get_order → get_product → request_exchange → done.
Copy identifiers byte-for-byte from customer message or tool results (never invent).
For color/variant exchanges: from_item_ids = item currently on the order;
to_item_ids = catalog id whose name matches the requested variant (e.g. black).
"""


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(rel: str) -> dict[str, Any]:
    path = package_root() / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid json object: {rel}")
    return data


def build_tools(state: dict[str, Any]) -> ToolSet:
    """Build ToolSet bound to mutable retail state."""
    ts = ToolSet(
        allowlist={
            "find_customer",
            "get_order",
            "get_product",
            "request_exchange",
            "done",
        }
    )

    def find_customer(args: dict[str, Any]) -> dict[str, Any]:
        email = str(args.get("email") or "")
        for cid, cust in (state.get("customers") or {}).items():
            if isinstance(cust, dict) and cust.get("email") == email:
                return {"ok": True, "customer_id": cid, "customer": cust}
        return {"ok": False, "error": "not_found"}

    def get_order(args: dict[str, Any]) -> dict[str, Any]:
        oid = str(args.get("order_id") or "")
        order = (state.get("orders") or {}).get(oid)
        if not isinstance(order, dict):
            return {"ok": False, "error": "not_found"}
        products = state.get("products") if isinstance(state.get("products"), dict) else {}
        line_items: list[dict[str, Any]] = []
        for iid in order.get("item_ids") or []:
            meta = products.get(str(iid)) if isinstance(products.get(str(iid)), dict) else {}
            line_items.append({"item_id": str(iid), **meta})
        # Full catalog so exchange targets (e.g. color variants) are discoverable.
        catalog = {
            str(k): v
            for k, v in products.items()
            if isinstance(v, dict)
        }
        return {
            "ok": True,
            "order_id": oid,
            "order": order,
            "line_items": line_items,
            "product_catalog": catalog,
        }

    def get_product(args: dict[str, Any]) -> dict[str, Any]:
        pid = str(args.get("item_id") or "")
        products = state.get("products") if isinstance(state.get("products"), dict) else {}
        prod = products.get(pid)
        if not isinstance(prod, dict):
            return {"ok": False, "error": "not_found"}
        # Surface siblings so black/color variants are visible after a get_product.
        siblings = {
            str(k): v
            for k, v in products.items()
            if isinstance(v, dict) and str(k) != pid
        }
        return {
            "ok": True,
            "item_id": pid,
            "product": prod,
            "other_products": siblings,
        }

    def request_exchange(args: dict[str, Any]) -> dict[str, Any]:
        oid = str(args.get("order_id") or "")
        frm = args.get("from_item_ids") or []
        to = args.get("to_item_ids") or []
        if not isinstance(frm, list) or not isinstance(to, list) or not frm or not to:
            return {"ok": False, "error": "bad_args"}
        order = (state.get("orders") or {}).get(oid)
        if not isinstance(order, dict):
            return {"ok": False, "error": "order_not_found"}
        if str(order.get("status") or "") != "delivered":
            return {"ok": False, "error": "order_not_delivered"}
        items = list(order.get("item_ids") or [])
        for x in frm:
            if str(x) not in items:
                return {"ok": False, "error": f"item_not_in_order:{x}"}
        products = state.get("products") if isinstance(state.get("products"), dict) else {}
        for t in to:
            if str(t) not in products:
                return {"ok": False, "error": f"unknown_target_product:{t}"}
        new_items = [i for i in items if i not in {str(x) for x in frm}] + [str(t) for t in to]
        order["item_ids"] = new_items
        order["status"] = "exchange_requested"
        rec = {
            "order_id": oid,
            "from_item_ids": [str(x) for x in frm],
            "to_item_ids": [str(t) for t in to],
        }
        exchanges = state.setdefault("exchanges", [])
        if isinstance(exchanges, list):
            exchanges.append(rec)
        return {"ok": True, "exchange": rec, "order": order}

    def done(args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "done": True, "note": args.get("note")}

    ts.add(Tool(name="find_customer", fn=find_customer, schema={"required": ["email"]}))
    ts.add(Tool(name="get_order", fn=get_order, schema={"required": ["order_id"]}))
    ts.add(Tool(name="get_product", fn=get_product, schema={"required": ["item_id"]}))
    ts.add(
        Tool(
            name="request_exchange",
            fn=request_exchange,
            schema={"required": ["order_id", "from_item_ids", "to_item_ids"]},
        )
    )
    ts.add(Tool(name="done", fn=done, schema={}))
    return ts


def workflow_allows(tools_used: list[str], tool_name: str) -> bool:
    """Gate tool by unlock prefix; done only after request_exchange."""
    if tool_name == "done":
        return "request_exchange" in tools_used
    if tool_name not in WORKFLOW_PREFIX:
        return False
    idx = WORKFLOW_PREFIX.index(tool_name)
    return all(prev in tools_used for prev in WORKFLOW_PREFIX[:idx])
