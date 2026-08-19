"""The one place an exclusive slot winner becomes a live object.

Resolution (``resolve.py``) decides *which* plugin wins and puts that in the
lock. It deliberately does not construct anything: the box needs the Attempt
work root, the executor needs the started box, and neither exists at lock time.
Binding therefore happens here, once, with the engine-owned context passed in.
"""

from __future__ import annotations

from typing import Any

from ageval.plugins.errors import ExtensionMaterializeError, ExtensionPluginNotFoundError
from ageval.plugins.protocol import ExtensionGraph
from ageval.plugins.registry import ExtensionRegistry


def bind_winner(
    registry: ExtensionRegistry,
    graph: ExtensionGraph,
    slot: str,
    **context: Any,
) -> Any:
    """Construct the winner of *slot* with engine-owned *context*."""
    winner = graph.winners.get(slot)
    if winner is None:
        raise ExtensionPluginNotFoundError(
            f"no plugin is bound to exclusive slot {slot!r}",
            kind="extension_plugin_not_found",
        )
    registration = registry.get_registration(slot, winner.plugin_id)
    if registration is None:
        raise ExtensionPluginNotFoundError(
            f"plugin {winner.plugin_id!r} no longer registers slot {slot!r}",
            kind="extension_plugin_not_found",
        )
    if not registration.is_factory:
        return registration.impl
    if not callable(registration.impl):
        raise ExtensionMaterializeError(
            f"factory for plugin {winner.plugin_id!r} slot {slot!r} is not callable",
            kind="extension_materialize_failed",
        )
    try:
        return registration.impl(options=dict(winner.options or {}), **context)
    except ExtensionMaterializeError:
        raise
    except Exception as exc:  # noqa: BLE001 — one bind failure, no retry
        raise ExtensionMaterializeError(
            f"bind failed for plugin {winner.plugin_id!r} slot {slot!r}: {exc}",
            kind="extension_materialize_failed",
        ) from exc
