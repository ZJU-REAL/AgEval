"""ageval plugin subsystem: fixed extension slots + registry (写法 B).

Public surface for composition root, config lock, and Agent Service.
Third-party business plugins do not live under this package.
"""

from __future__ import annotations

from ageval.plugins.conflict import ExtensionConflictError
from ageval.plugins.errors import (
    ExtensionMaterializeError,
    ExtensionPluginNotFoundError,
    ExtensionRegistryError,
    UnknownExtensionSlotError,
)
from ageval.plugins.lock_bind import extension_graph_to_lock
from ageval.plugins.middleware import run_chain
from ageval.plugins.protocol import (
    BindingIntent,
    ExplicitBinding,
    ExtensionGraph,
    HandlerRef,
    ProviderRef,
)
from ageval.plugins.registry import ExtensionRegistry, get_global_registry, reset_global_registry
from ageval.plugins.resolve import resolve
from ageval.plugins.slots import ALL_PUBLIC_SLOTS, SlotKind, get_slot_kind, is_public_slot

__all__ = [
    "ALL_PUBLIC_SLOTS",
    "BindingIntent",
    "ExplicitBinding",
    "ExtensionConflictError",
    "ExtensionGraph",
    "ExtensionMaterializeError",
    "ExtensionPluginNotFoundError",
    "ExtensionRegistry",
    "ExtensionRegistryError",
    "HandlerRef",
    "ProviderRef",
    "SlotKind",
    "UnknownExtensionSlotError",
    "extension_graph_to_lock",
    "get_global_registry",
    "get_slot_kind",
    "is_public_slot",
    "reset_global_registry",
    "resolve",
    "run_chain",
]
