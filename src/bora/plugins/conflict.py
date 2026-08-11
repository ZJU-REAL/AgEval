"""Conflict resolution: explicit binding > numeric priority; ties fail closed.

Priority convention (documented):
- **Lower number wins** for provide (single winner).
- **Lower number runs first** for multi (chain order).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bora.plugins.errors import ExtensionPluginNotFoundError, ExtensionRegistryError
from bora.plugins.protocol import ExplicitBinding


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
    """Select the single provide winner or raise ExtensionConflictError."""
    if not candidates and not explicit:
        raise ExtensionPluginNotFoundError(
            f"no providers registered for slot {slot!r}",
            kind="extension_plugin_not_found",
        )

    by_plugin = {c.plugin_id: c for c in candidates}
    # Last explicit for this slot wins among explicits (profiles order).
    slot_explicit = [e for e in explicit if e.slot == slot]
    if slot_explicit:
        chosen_binding = slot_explicit[-1]
        cand = by_plugin.get(chosen_binding.plugin)
        if cand is None:
            raise ExtensionPluginNotFoundError(
                f"plugin {chosen_binding.plugin!r} has no provide for slot {slot!r}",
                kind="extension_plugin_not_found",
            )
        # Explicit may override priority for lock record; keep registered impl.
        prio = (
            int(chosen_binding.priority)
            if chosen_binding.priority is not None
            else cand.priority
        )
        return Candidate(
            plugin_id=cand.plugin_id,
            impl=cand.impl,
            priority=prio,
            source=chosen_binding.source or "explicit",
            version=cand.version,
            digest=cand.digest,
            is_default=cand.is_default,
        )

    if not candidates:
        raise ExtensionPluginNotFoundError(
            f"no providers registered for slot {slot!r}",
            kind="extension_plugin_not_found",
        )

    # Lowest priority number wins; tie → fail closed.
    best_prio = min(c.priority for c in candidates)
    winners = [c for c in candidates if c.priority == best_prio]
    if len(winners) > 1:
        ids = sorted({c.plugin_id for c in winners})
        raise ExtensionConflictError(
            f"extension conflict on slot {slot!r}: equal priority {best_prio} "
            f"among {ids} without explicit binding",
            kind="extension_conflict",
        )
    return winners[0]


def order_chain(
    candidates: list[Candidate],
    explicit: list[ExplicitBinding],
    *,
    slot: str,
) -> list[Candidate]:
    """Order multi-slot handlers; apply replace_default and explicit priority.

    Returns chain sorted by ascending priority (lower runs first).
    """
    by_plugin = {c.plugin_id: c for c in candidates}
    slot_explicit = [e for e in explicit if e.slot == slot]

    # Start from registered candidates.
    selected: dict[str, Candidate] = {c.plugin_id: c for c in candidates}

    replace_default = any(e.replace_default for e in slot_explicit)
    if replace_default:
        selected = {pid: c for pid, c in selected.items() if not c.is_default}

    for binding in slot_explicit:
        cand = by_plugin.get(binding.plugin)
        if cand is None:
            raise ExtensionPluginNotFoundError(
                f"plugin {binding.plugin!r} has no on() for slot {slot!r}",
                kind="extension_plugin_not_found",
            )
        prio = int(binding.priority) if binding.priority is not None else cand.priority
        selected[binding.plugin] = Candidate(
            plugin_id=cand.plugin_id,
            impl=cand.impl,
            priority=prio,
            source=binding.source or "explicit",
            version=cand.version,
            digest=cand.digest,
            is_default=cand.is_default,
        )

    ordered = sorted(selected.values(), key=lambda c: (c.priority, c.plugin_id))
    # Detect equal-priority ties only when neither is default-only chain of one
    # and there is no explicit that differentiated them — multi allows same
    # priority only if plugin_ids differ and we use plugin_id as stable tiebreak.
    # Fail closed when two non-default contributions share priority with no
    # explicit for either.
    if len(ordered) >= 2:
        from collections import defaultdict

        buckets: dict[int, list[Candidate]] = defaultdict(list)
        for c in ordered:
            buckets[c.priority].append(c)
        for prio, group in buckets.items():
            if len(group) < 2:
                continue
            # Defaults among themselves: allow stable plugin_id order.
            if all(c.is_default for c in group):
                continue
            non_default = [c for c in group if not c.is_default]
            if len(non_default) < 2:
                continue
            # If every member of the tie has an explicit binding for this slot, OK.
            explicit_plugins = {e.plugin for e in slot_explicit}
            if all(c.plugin_id in explicit_plugins for c in non_default):
                continue
            ids = sorted(c.plugin_id for c in non_default)
            raise ExtensionConflictError(
                f"extension conflict on multi slot {slot!r}: equal priority "
                f"{prio} among {ids} without explicit binding",
                kind="extension_conflict",
            )
    return ordered
