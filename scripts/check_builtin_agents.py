#!/usr/bin/env python3
"""Fail if builtin agent catalog drifts from shipped trees (design/14).

Does not import ageval.plugins.contrib. Does not publish.

Run: uv run python scripts/check_builtin_agents.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "src" / "ageval" / "agents" / "builtin" / "catalog.json"
ACP_ENTRIES = REPO / "src" / "ageval" / "plugins" / "contrib" / "acp" / "acp_entries.json"
ROW_KEYS = frozenset({"harness_id", "kind", "product", "label", "description"})
KINDS = frozenset({"acp", "executor"})


def _fail(message: str) -> int:
    print(f"check_builtin_agents: {message}", file=sys.stderr)
    return 1


def _acp_entry_ids() -> set[str]:
    raw = json.loads(ACP_ENTRIES.read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError("acp_entries.json missing entries list")
    out: set[str] = set()
    for item in entries:
        if isinstance(item, dict) and isinstance(item.get("entry_id"), str):
            out.add(item["entry_id"])
    return out


def _binding_entry(binding: dict[str, Any]) -> str:
    extensions = binding.get("extensions")
    if not isinstance(extensions, list):
        return ""
    for row in extensions:
        if not isinstance(row, dict):
            continue
        if str(row.get("plugin") or "").strip() != "acp":
            continue
        options = row.get("options")
        if isinstance(options, dict):
            return str(options.get("entry") or "").strip()
    return ""


def main() -> int:
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        return _fail("catalog must be a nonempty JSON list")

    from ageval.agents.manifest import load_agent_manifest
    from ageval.agents.reserved import builtin_harness_ids, builtin_harness_root

    catalog_ids: list[str] = []
    seen: set[str] = set()
    try:
        acp_ids = _acp_entry_ids()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _fail(f"cannot read acp_entries.json: {exc}")

    for item in raw:
        if not isinstance(item, dict) or set(item) != ROW_KEYS:
            return _fail("each row keys must be harness_id, kind, product, label, description")
        harness_id = item["harness_id"]
        kind = item["kind"]
        product = item["product"]
        if not isinstance(harness_id, str) or not harness_id or "/" in harness_id:
            return _fail(f"invalid harness_id {harness_id!r}")
        if harness_id in seen:
            return _fail(f"duplicate harness_id {harness_id!r}")
        if kind not in KINDS:
            return _fail(f"{harness_id}: kind must be acp or executor")
        if not isinstance(product, str) or not product.strip():
            return _fail(f"{harness_id}: product required")
        if not isinstance(item["label"], str) or not item["label"].strip():
            return _fail(f"{harness_id}: label required")
        if not isinstance(item["description"], str) or not item["description"].strip():
            return _fail(f"{harness_id}: description required")
        seen.add(harness_id)
        catalog_ids.append(harness_id)

        root = builtin_harness_root(harness_id)
        manifest_path = root / "agent.yaml"
        if not manifest_path.is_file():
            return _fail(f"{harness_id}: missing {manifest_path.relative_to(REPO)}")
        man = load_agent_manifest(root)
        if man.agent_id != harness_id:
            return _fail(f"{harness_id}: agent.yaml agent_id is {man.agent_id!r}")
        if man.label != item["label"]:
            return _fail(f"{harness_id}: agent.yaml label drifted from catalog")
        if "model" in man.binding:
            return _fail(f"{harness_id}: builtin trees must not set binding.model")
        executor = str(man.binding.get("executor") or "").strip()
        if kind == "acp":
            if product not in acp_ids:
                return _fail(f"{harness_id}: product {product!r} not in acp_entries.json")
            if executor != "acp":
                return _fail(f"{harness_id}: executor must be acp")
            entry = _binding_entry(man.binding)
            if entry != product:
                return _fail(f"{harness_id}: ACP entry {entry!r} != product {product!r}")
        else:
            if executor != product or product != harness_id:
                return _fail(f"{harness_id}: executor-kind product must equal harness_id")

        overlays = man.binding.get("overlays")
        if isinstance(overlays, list):
            for declared in overlays:
                rel = str(declared).strip()
                if not rel:
                    continue
                if not (root / rel).is_file():
                    return _fail(f"{harness_id}: missing overlay file {rel}")

    if set(catalog_ids) != builtin_harness_ids():
        return _fail("reserved.py ids drifted from catalog.json")

    extra_dirs = [
        p.name
        for p in CATALOG.parent.iterdir()
        if p.is_dir() and p.name != "__pycache__" and p.name not in seen
    ]
    if extra_dirs:
        return _fail(f"tree without catalog row: {sorted(extra_dirs)}")

    print(f"check_builtin_agents: ok ({len(catalog_ids)} harness ids)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
