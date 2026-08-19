"""Serialize ExtensionGraph → lock ``extension_bindings`` document fragment."""

from __future__ import annotations

from typing import Any

from ageval.plugins.protocol import ExtensionGraph


def extension_graph_to_lock(graph: ExtensionGraph) -> dict[str, Any]:
    """Project one profile's graph into the lock binding shape."""
    slots: dict[str, Any] = {}

    for slot, ref in graph.winners.items():
        row: dict[str, Any] = {
            "kind": "exclusive",
            "plugin": ref.plugin_id,
            "priority": ref.priority,
            "source": ref.source,
        }
        if ref.version is not None:
            row["version"] = ref.version
        if ref.digest is not None:
            row["digest"] = ref.digest
        slots[slot] = row

    for slot, chain in graph.chains.items():
        slots[slot] = {
            "kind": "chain",
            "chain": [
                {
                    "plugin": h.plugin_id,
                    "priority": h.priority,
                    "source": h.source,
                    **({"version": h.version} if h.version is not None else {}),
                    **({"digest": h.digest} if h.digest is not None else {}),
                }
                for h in chain
            ],
        }

    out: dict[str, Any] = {"slots": slots}
    if graph.services:
        out["services"] = dict(sorted(graph.services.items()))
    if graph.injects:
        out["inject"] = {
            plugin_id: [
                {
                    "service": row.service,
                    **({"capabilities": list(row.capabilities)} if row.capabilities else {}),
                }
                for row in rows
            ]
            for plugin_id, rows in sorted(graph.injects.items())
        }
    return out


def extension_bindings_for_profiles(
    graphs: dict[str, ExtensionGraph],
) -> dict[str, dict[str, Any]]:
    """Map profile id → lock extension_bindings subtree."""
    return {pid: extension_graph_to_lock(g) for pid, g in graphs.items()}


def winner_plugin(lock_fragment: dict[str, Any], slot: str) -> str | None:
    """Plugin id bound to *slot* in a lock fragment, if any."""
    row = (lock_fragment.get("slots") or {}).get(slot)
    if not isinstance(row, dict) or row.get("kind") != "exclusive":
        return None
    plugin = row.get("plugin")
    return str(plugin) if plugin else None
