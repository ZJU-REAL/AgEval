"""Extension registry: on (multi) / provide (single) registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bora.plugins.conflict import Candidate
from bora.plugins.errors import UnknownExtensionSlotError
from bora.plugins.slots import DEFAULT_PRIORITY, get_slot_kind, is_public_slot


@dataclass
class Registration:
    """One on/provide registration row."""

    slot: str
    plugin_id: str
    impl: Any  # concrete SPI / handler / factory
    priority: int
    source: str
    version: str | None = None
    digest: str | None = None
    is_default: bool = False
    is_factory: bool = False


@dataclass
class ExtensionRegistry:
    """In-memory registry of extension contributions.

    Same plugin_id re-registering the same slot **overwrites** the previous row
    (last write wins for that plugin); the winning registration's source is what
    lock records after resolve.
    """

    _rows: dict[str, dict[str, Registration]] = field(default_factory=dict)

    def provide(
        self,
        slot: str,
        plugin_id: str,
        impl: Any,
        *,
        priority: int = DEFAULT_PRIORITY,
        source: str = "installed",
        version: str | None = None,
        digest: str | None = None,
        is_default: bool = False,
        is_factory: bool = False,
    ) -> None:
        self._register(
            slot,
            plugin_id,
            impl,
            priority=priority,
            source=source,
            version=version,
            digest=digest,
            is_default=is_default,
            is_factory=is_factory,
            expect_kind="provide",
        )

    def on(
        self,
        slot: str,
        plugin_id: str,
        handler: Any,
        *,
        priority: int = DEFAULT_PRIORITY,
        source: str = "installed",
        version: str | None = None,
        digest: str | None = None,
        is_default: bool = False,
        is_factory: bool = False,
    ) -> None:
        self._register(
            slot,
            plugin_id,
            handler,
            priority=priority,
            source=source,
            version=version,
            digest=digest,
            is_default=is_default,
            is_factory=is_factory,
            expect_kind="multi",
        )

    def _register(
        self,
        slot: str,
        plugin_id: str,
        impl: Any,
        *,
        priority: int,
        source: str,
        version: str | None,
        digest: str | None,
        is_default: bool,
        is_factory: bool,
        expect_kind: str,
    ) -> None:
        if not is_public_slot(slot):
            raise UnknownExtensionSlotError(
                f"unknown extension slot: {slot!r}",
                kind="unknown_extension_slot",
            )
        kind = get_slot_kind(slot)
        if expect_kind == "provide" and kind.value != "provide":
            raise UnknownExtensionSlotError(
                f"slot {slot!r} is multi; use on(), not provide()",
                kind="unknown_extension_slot",
            )
        if expect_kind == "multi" and kind.value != "multi":
            raise UnknownExtensionSlotError(
                f"slot {slot!r} is provide; use provide(), not on()",
                kind="unknown_extension_slot",
            )
        slot_map = self._rows.setdefault(slot, {})
        slot_map[plugin_id] = Registration(
            slot=slot,
            plugin_id=plugin_id,
            impl=impl,
            priority=int(priority),
            source=source,
            version=version,
            digest=digest,
            is_default=is_default,
            is_factory=is_factory,
        )

    def candidates(self, slot: str) -> list[Candidate]:
        if not is_public_slot(slot):
            raise UnknownExtensionSlotError(
                f"unknown extension slot: {slot!r}",
                kind="unknown_extension_slot",
            )
        rows = self._rows.get(slot) or {}
        return [
            Candidate(
                plugin_id=r.plugin_id,
                impl=r,
                priority=r.priority,
                source=r.source,
                version=r.version,
                digest=r.digest,
                is_default=r.is_default,
            )
            for r in rows.values()
        ]

    def get_registration(self, slot: str, plugin_id: str) -> Registration | None:
        return (self._rows.get(slot) or {}).get(plugin_id)

    def plugins_for_slot(self, slot: str) -> list[str]:
        return sorted((self._rows.get(slot) or {}).keys())

    def slots_for_plugin(self, plugin_id: str) -> list[str]:
        """Public slots this plugin registered (provide + on)."""
        found: list[str] = []
        for slot, rows in self._rows.items():
            if plugin_id in rows:
                found.append(slot)
        return found

    def clear(self) -> None:
        self._rows.clear()


_GLOBAL: ExtensionRegistry | None = None


def get_global_registry() -> ExtensionRegistry:
    """Process-local registry used by production composition (tests may replace)."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = ExtensionRegistry()
    return _GLOBAL


def reset_global_registry() -> ExtensionRegistry:
    """Reset and return a fresh global registry (tests / re-bootstrap)."""
    global _GLOBAL
    _GLOBAL = ExtensionRegistry()
    return _GLOBAL
