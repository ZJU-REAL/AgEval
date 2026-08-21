"""Extension registry: exclusive (one winner) / chain (ordered handlers)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ageval.plugins.conflict import Candidate
from ageval.plugins.errors import UnknownExtensionSlotError
from ageval.plugins.slots import DEFAULT_PRIORITY, SlotKind, get_slot_kind, is_slot


@dataclass
class Registration:
    """One exclusive/chain registration row."""

    slot: str
    plugin_id: str
    impl: Any  # concrete object, handler, or factory
    priority: int
    source: str
    version: str | None = None
    digest: str | None = None
    is_default: bool = False
    is_factory: bool = False


@dataclass
class ServiceRegistration:
    """One ``exports.services`` row (name → factory/object)."""

    service_id: str
    plugin_id: str
    impl: Any
    source: str
    is_factory: bool = False


@dataclass
class ExtensionRegistry:
    """In-memory registry of extension contributions.

    Same plugin re-registering the same slot overwrites its own row.
    """

    _rows: dict[str, dict[str, Registration]] = field(default_factory=dict)
    _services: dict[str, ServiceRegistration] = field(default_factory=dict)
    _injects: dict[str, tuple[Any, ...]] = field(default_factory=dict)

    def exclusive(
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
            expect=SlotKind.EXCLUSIVE,
        )

    def chain(
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
            expect=SlotKind.CHAIN,
        )

    def export_service(
        self,
        service_id: str,
        plugin_id: str,
        impl: Any,
        *,
        source: str = "installed",
        is_factory: bool = False,
    ) -> None:
        """Register a named service. Two plugins exporting one id fail closed."""
        sid = service_id.strip()
        if not sid:
            raise UnknownExtensionSlotError("service id required", kind="service_not_found")
        from ageval.plugins.services import RESERVED_SERVICE_IDS

        if sid in RESERVED_SERVICE_IDS:
            from ageval.plugins.errors import ServiceConflictError

            raise ServiceConflictError(
                f"service {sid!r} is an engine invariant and cannot be provided by a plugin",
                kind="service_conflict",
            )
        if is_slot(sid):
            from ageval.plugins.errors import ServiceConflictError

            raise ServiceConflictError(
                f"service id {sid!r} collides with a slot name (exclusive winners "
                "already register under their slot name)",
                kind="service_conflict",
            )
        found = self._services.get(sid)
        if found is not None and found.plugin_id != plugin_id:
            from ageval.plugins.errors import ServiceConflictError

            raise ServiceConflictError(
                f"service {sid!r} exported by both {found.plugin_id!r} and {plugin_id!r}",
                kind="service_conflict",
            )
        self._services[sid] = ServiceRegistration(
            service_id=sid,
            plugin_id=plugin_id,
            impl=impl,
            source=source,
            is_factory=is_factory,
        )

    def declare_inject(self, plugin_id: str, rows: tuple[Any, ...]) -> None:
        """Record the services *plugin_id* will call (checked at lock time)."""
        if rows:
            self._injects[plugin_id] = tuple(rows)

    def injects_for_plugin(self, plugin_id: str) -> tuple[Any, ...]:
        return self._injects.get(plugin_id) or ()

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
        expect: SlotKind,
    ) -> None:
        kind = get_slot_kind(slot)
        if kind is not expect:
            raise UnknownExtensionSlotError(
                f"slot {slot!r} is {kind.value}; register it with {kind.value}()",
                kind="unknown_extension_slot",
            )
        self._rows.setdefault(slot, {})[plugin_id] = Registration(
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
        if not is_slot(slot):
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
        return [slot for slot, rows in self._rows.items() if plugin_id in rows]

    def service(self, service_id: str) -> ServiceRegistration | None:
        return self._services.get(service_id)

    def services_for_plugin(self, plugin_id: str) -> list[str]:
        return sorted(sid for sid, row in self._services.items() if row.plugin_id == plugin_id)

    def clear(self) -> None:
        self._rows.clear()
        self._services.clear()
        self._injects.clear()


_GLOBAL: ExtensionRegistry | None = None


def get_global_registry() -> ExtensionRegistry:
    """Process-local registry used by production composition."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = ExtensionRegistry()
    return _GLOBAL


def reset_global_registry() -> ExtensionRegistry:
    """Reset and return a fresh global registry (re-bootstrap)."""
    global _GLOBAL
    _GLOBAL = ExtensionRegistry()
    return _GLOBAL
