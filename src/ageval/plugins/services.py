"""Service table: what exists in this Attempt that a plugin may call by name.

Exclusive slot winners register under their slot name (``environment``,
``executor``). Plugins may export extra named services. Dependencies are always
declared as ``inject: [service: <name>]`` — never as ``plugin_id`` — so swapping
the winner does not touch the caller.

PASS, Attempt identity and cleanup are engine invariants and are never services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ageval.plugins.errors import (
    InjectUnsatisfiedError,
    ServiceConflictError,
    ServiceNotFoundError,
)
from ageval.plugins.protocol import InjectRequirement

# Names the engine owns; a plugin export may never take them over.
RESERVED_SERVICE_IDS: frozenset[str] = frozenset({"pass", "identity", "cleanup", "evidence"})


@dataclass
class ServiceTable:
    """Name → object for one Attempt."""

    _items: dict[str, Any] = field(default_factory=dict)
    _owners: dict[str, str] = field(default_factory=dict)

    def register(self, service_id: str, impl: Any, *, plugin_id: str) -> None:
        sid = service_id.strip()
        if not sid:
            raise ServiceNotFoundError("service id required")
        if sid in RESERVED_SERVICE_IDS:
            raise ServiceConflictError(
                f"service {sid!r} is an engine invariant and cannot be provided by a plugin"
            )
        owner = self._owners.get(sid)
        if owner is not None and owner != plugin_id:
            raise ServiceConflictError(
                f"service {sid!r} claimed by both {owner!r} and {plugin_id!r}"
            )
        self._items[sid] = impl
        self._owners[sid] = plugin_id

    def require(self, service_id: str) -> Any:
        try:
            return self._items[service_id]
        except KeyError as exc:
            raise ServiceNotFoundError(f"service not available: {service_id!r}") from exc

    def get(self, service_id: str) -> Any | None:
        return self._items.get(service_id)

    def owner(self, service_id: str) -> str | None:
        return self._owners.get(service_id)

    def names(self) -> list[str]:
        return sorted(self._items)


def assert_inject_satisfied(
    injects: dict[str, tuple[InjectRequirement, ...]],
    available: dict[str, Any],
) -> None:
    """Lock-time inject check: service present and caps deliverable.

    *available* maps service id → the resolved winner/export object. A required
    capability is checked against the object's ``capabilities`` when it declares
    them (environment kinds do), so a box that cannot ``attach_stdio`` fails the
    lock instead of failing mid-invoke.
    """
    for plugin_id, rows in sorted(injects.items()):
        for row in rows:
            impl = available.get(row.service)
            if impl is None:
                raise InjectUnsatisfiedError(
                    f"plugin {plugin_id!r} injects service {row.service!r} "
                    "but no plugin provides it"
                )
            if not row.capabilities:
                continue
            caps = getattr(impl, "capabilities", None)
            if caps is None:
                raise InjectUnsatisfiedError(
                    f"plugin {plugin_id!r} requires capabilities "
                    f"{list(row.capabilities)} from service {row.service!r} "
                    "which declares none"
                )
            missing = _missing_capabilities(caps, row.capabilities)
            if missing:
                raise InjectUnsatisfiedError(
                    f"plugin {plugin_id!r} requires {missing} from service "
                    f"{row.service!r} which does not provide them"
                )


def _missing_capabilities(caps: Any, wanted: tuple[str, ...]) -> list[str]:
    missing_fn = getattr(caps, "missing", None)
    if callable(missing_fn):
        found: Any = missing_fn(wanted)
        return [str(name) for name in list(found)]
    return sorted({name for name in wanted if not getattr(caps, name, False)})
