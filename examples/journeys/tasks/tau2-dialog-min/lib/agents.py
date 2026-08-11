"""Deterministic package agents for nooa executor (tau2 retail dialog)."""

from __future__ import annotations

import json
import re
from typing import Any


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class UserSimAgent:
    """Emit one customer message embedding email + known_order_id from private facts."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del workdir
        email = "alex@example.com"
        order_id = "#W1001"
        # Prefer facts embedded in the prompt (harness dumps private JSON).
        blob = _parse_json_blob(prompt)
        if isinstance(blob, dict):
            if blob.get("email"):
                email = str(blob["email"])
            if blob.get("known_order_id"):
                order_id = str(blob["known_order_id"])
        else:
            m_email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", prompt)
            m_order = re.search(r"#W\d+", prompt)
            if m_email:
                email = m_email.group(0)
            if m_order:
                order_id = m_order.group(0)
        message = (
            f"Hi, my email is {email}. I received order {order_id} but the headphones "
            "are the wrong color — I want the black variant instead."
        )
        payload = {"message": message}
        return {"ok": True, "text": json.dumps(payload), "structured": payload}


class ServiceAgent:
    """Drive the fixed retail tool workflow without inventing identifiers."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del workdir
        observations: list[dict[str, Any]] = []
        # Extract observations JSON array from the prompt if present.
        obs_key = "Tool observations (authoritative):\n"
        if obs_key in prompt:
            tail = prompt.split(obs_key, 1)[1]
            # Array starts at first '['
            lb = tail.find("[")
            if lb >= 0:
                # Find matching end by JSON parse attempts
                for rb in range(len(tail), lb, -1):
                    try:
                        val = json.loads(tail[lb:rb])
                        if isinstance(val, list):
                            observations = [x for x in val if isinstance(x, dict)]
                            break
                    except json.JSONDecodeError:
                        continue

        email_m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", prompt)
        order_m = re.search(r"#W\d+", prompt)
        email = email_m.group(0) if email_m else "alex@example.com"
        order_id = order_m.group(0) if order_m else "#W1001"

        used = [str(o.get("tool") or "") for o in observations if o.get("tool")]

        def _ok(tool: str) -> bool:
            for o in observations:
                if o.get("tool") == tool and isinstance(o.get("result"), dict) and o["result"].get(
                    "ok"
                ):
                    return True
            return False

        if not _ok("find_customer"):
            action = {"tool": "find_customer", "args": {"email": email}}
        elif not _ok("get_order"):
            action = {"tool": "get_order", "args": {"order_id": order_id}}
        elif not _ok("get_product"):
            action = {"tool": "get_product", "args": {"item_id": "item_headphones"}}
        elif not _ok("request_exchange"):
            action = {
                "tool": "request_exchange",
                "args": {
                    "order_id": order_id,
                    "from_item_ids": ["item_headphones"],
                    "to_item_ids": ["item_headphones_black"],
                },
            }
        elif "done" not in used:
            action = {"tool": "done", "args": {"note": "exchange requested"}}
        else:
            action = {"tool": "done", "args": {"note": "already done"}}

        return {"ok": True, "text": json.dumps(action), "structured": action}
