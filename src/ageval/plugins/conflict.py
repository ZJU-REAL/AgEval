"""Conflict resolution: explicit binding > numeric priority; ties fail closed.

Lower number wins an exclusive slot and runs first in a chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ageval.plugins.errors import ExtensionPluginNotFoundError, ExtensionRegistryError
from ageval.plugins.protocol import ExplicitBinding


class ExtensionConflictError(ExtensionRegistryError):
    kind = "extension_conflict"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One registered contribution considered for a slot."""

    plugin_id: str
    impl: Any
    priority: int
    source: str  # default | installed | first-party | …
    version: str | None = None
    digest: str | None = None
    is_default: bool = False


def pick_one(
    candidates: list[Candidate],
    explicit: list[ExplicitBinding],
    *,
    slot: str,
) -> Candidate:
    """Select the single exclusive winner or fail closed."""
    by_plugin = {c.plugin_id: c for c in candidates}
    slot_explicit = [e for e in explicit if e.slot == slot]
    if slot_explicit:
        chosen = slot_explicit[-1]
        cand = by_plugin.get(chosen.plugin)
        if cand is None:
            raise ExtensionPluginNotFoundError(
                f"plugin {chosen.plugin!r} does not fill exclusive slot {slot!r} "
                f"(registered: {sorted(by_plugin)})",
                kind="extension_plugin_not_found",
            )
        priority = int(chosen.priority) if chosen.priority is not None else cand.priority
        return Candidate(
            plugin_id=cand.plugin_id,
            impl=cand.impl,
            priority=priority,
            source=chosen.source or "explicit",
            version=cand.version,
            digest=cand.digest,
            is_default=cand.is_default,
        )

    if not candidates:
        raise ExtensionPluginNotFoundError(
            f"no plugin fills exclusive slot {slot!r}",
            kind="extension_plugin_not_found",
        )

    best = min(c.priority for c in candidates)
    winners = [c for c in candidates if c.priority == best]
    if len(winners) > 1:
        ids = sorted({c.plugin_id for c in winners})
        raise ExtensionConflictError(
            f"exclusive slot {slot!r} claimed at equal priority {best} by {ids}",
            kind="extension_conflict",
        )
    return winners[0]


def order_chain(
    candidates: list[Candidate],
    explicit: list[ExplicitBinding],
    *,
    slot: str,
) -> list[Candidate]:
    """Order chain handlers: defaults / first-party join automatically, others opt in."""
    by_plugin = {c.plugin_id: c for c in candidates}
    slot_explicit = [e for e in explicit if e.slot == slot]
    selected: dict[str, Candidate] = {
        c.plugin_id: c for c in candidates if c.is_default or c.source in {"default", "first-party"}
    }
    for binding in slot_explicit:
        cand = by_plugin.get(binding.plugin)
        if cand is None:
            raise ExtensionPluginNotFoundError(
                f"plugin {binding.plugin!r} has no handler for chain slot {slot!r}",
                kind="extension_plugin_not_found",
            )
        priority = int(binding.priority) if binding.priority is not None else cand.priority
        selected[binding.plugin] = Candidate(
            plugin_id=cand.plugin_id,
            impl=cand.impl,
            priority=priority,
            source=binding.source or "explicit",
            version=cand.version,
            digest=cand.digest,
            is_default=cand.is_default,
        )
    return sorted(selected.values(), key=lambda c: (c.priority, c.plugin_id))
