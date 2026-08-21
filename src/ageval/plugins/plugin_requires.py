"""Evaluate ``plugin_requires`` against the local plugin cache.

This is a cache-graph check, not a host extra. Exact ``plugin_id`` match only.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ageval.plugins.host_requires import installed_plugin
from ageval.plugins.manifest import PluginManifest, PluginRequire
from ageval.plugins.store import IndexEntry, list_installed


class PluginRequiresError(Exception):
    """Unsatisfied or cyclic plugin_requires (fail closed)."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def plugin_requires_satisfied(requires: Sequence[PluginRequire]) -> bool:
    if not requires:
        return True
    return all(installed_plugin(item.plugin_id) is not None for item in requires)


def evaluate_plugin_requires(
    requires: Sequence[PluginRequire],
    *,
    plugin_id: str,
) -> list[dict[str, Any]]:
    """One check dict per declared row. No secret values."""
    checks: list[dict[str, Any]] = []
    for item in requires:
        ok = installed_plugin(item.plugin_id) is not None
        row: dict[str, Any] = {
            "id": "plugin_requires",
            "ok": ok,
            "status": "ok" if ok else "missing",
            "required": item.plugin_id,
            "plugin": plugin_id,
        }
        if item.hint:
            row["hint"] = item.hint
        checks.append(row)
    return checks


def assert_no_plugin_requires_cycle(plugin_id: str, *, stack: tuple[str, ...] = ()) -> None:
    """Walk installed requires; raise on A → … → A."""
    if plugin_id in stack:
        chain = " -> ".join((*stack, plugin_id))
        raise PluginRequiresError(
            f"plugin_requires cycle: {chain}",
            kind="plugin_requires_cycle",
        )
    found = installed_plugin(plugin_id)
    if found is None:
        return
    manifest, _root = found
    nxt = (*stack, plugin_id)
    for item in manifest.plugin_requires:
        assert_no_plugin_requires_cycle(item.plugin_id, stack=nxt)


def assert_plugin_requires_installed(manifest: PluginManifest) -> None:
    """Fail closed when a declared neighbor is missing or the graph cycles."""
    assert_no_plugin_requires_cycle(manifest.plugin_id)
    missing = [
        item for item in manifest.plugin_requires if installed_plugin(item.plugin_id) is None
    ]
    if not missing:
        return
    first = missing[0]
    hint = f" ({first.hint})" if first.hint else ""
    raise PluginRequiresError(
        f"plugin {manifest.plugin_id!r} requires {first.plugin_id!r}{hint}",
        kind="plugin_requires_unsatisfied",
    )


def list_row_with_requires(entry: IndexEntry) -> dict[str, Any]:
    """Index row plus live ``plugin_requires`` satisfaction."""
    row = entry.as_dict()
    found = installed_plugin(entry.plugin_id)
    if found is None:
        row["plugin_requires_ok"] = False
        row["plugin_requires"] = []
        return row
    manifest, _root = found
    checks = evaluate_plugin_requires(manifest.plugin_requires, plugin_id=entry.plugin_id)
    ok = all(bool(c.get("ok")) for c in checks) if checks else True
    row["plugin_requires_ok"] = ok
    row["plugin_requires"] = [
        {
            "plugin_id": c["required"],
            "ok": c["ok"],
            **({"hint": c["hint"]} if c.get("hint") else {}),
        }
        for c in checks
    ]
    return row


def installed_plugin_ids() -> set[str]:
    return {entry.plugin_id for entry in list_installed()}
