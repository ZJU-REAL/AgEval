"""Deterministic package agent for nooa executor (jsonl aggregation)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class JsonlAggAgent:
    """Read records_*.jsonl in workdir and write aggregates.json."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del prompt
        root = Path(workdir or ".").expanduser().resolve(strict=False)
        users: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"total_amount": 0.0, "total_items": 0}
        )
        tag_counts: dict[str, int] = defaultdict(int)

        for path in sorted(root.glob("records_*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                user = str(row.get("user") or "")
                amount = float(row.get("amount") or 0.0)
                items = int(row.get("items") or 0)
                users[user]["total_amount"] = float(users[user]["total_amount"]) + amount
                users[user]["total_items"] = int(users[user]["total_items"]) + items
                for tag in row.get("tags") or []:
                    tag_counts[str(tag)] += 1

        # Top 5 users: amount desc, items desc, name asc
        user_ranked = sorted(
            users.items(),
            key=lambda kv: (-float(kv[1]["total_amount"]), -int(kv[1]["total_items"]), kv[0]),
        )[:5]
        top_users = {
            name: {
                "total_amount": round(float(stats["total_amount"]), 2),
                "total_items": int(stats["total_items"]),
            }
            for name, stats in user_ranked
        }
        # Top 5 tags: count desc, name asc
        tag_ranked = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        top_tags = {name: {"count": count} for name, count in tag_ranked}

        data = {
            "top_5_users_by_amount": top_users,
            "top_5_tags_by_count": top_tags,
        }
        out = root / "aggregates.json"
        out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "text": json.dumps(data),
            "structured": data,
        }
