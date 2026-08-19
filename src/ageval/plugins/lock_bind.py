"""Serialize ExtensionGraph → lock ``extension_bindings`` document fragment."""

from __future__ import annotations

from typing import Any

from ageval.plugins.protocol import ExtensionGraph


def extension_graph_to_lock(graph: ExtensionGraph) -> dict[str, Any]:
    """Project one profile's graph into the constitution §7.4 lock shape."""
    out: dict[str, Any] = {}

    for slot, pref in graph.providers.items():
        out[slot] = {
            "kind": "provide",
            "plugin": pref.plugin_id,
            "priority": pref.priority,
            "source": pref.source,
            "replaced_default": pref.replaced_default,
        }
        if pref.version is not None:
            out[slot]["version"] = pref.version
        if pref.digest is not None:
            out[slot]["digest"] = pref.digest

    for slot, chain in graph.chains.items():
        out[slot] = {
            "kind": "on",
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

    return out


def extension_bindings_for_profiles(
    graphs: dict[str, ExtensionGraph],
) -> dict[str, dict[str, Any]]:
    """Map profile_id → lock extension_bindings subtree."""
    return {pid: extension_graph_to_lock(g) for pid, g in graphs.items()}


def summarize_executor_binding(lock_fragment: dict[str, Any]) -> dict[str, Any] | None:
    """Helper for tests: extract executor provide row if present."""
    row = lock_fragment.get("executor")
    if not isinstance(row, dict):
        return None
    if row.get("kind") != "provide":
        return None
    return row
