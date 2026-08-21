"""e2b box: the Attempt runs in a cloud sandbox built from the task's recipe."""

from __future__ import annotations

from ageval.plugins.contrib.e2b.host import E2BHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "e2b"
E2B_PRIORITY = 100


def register_e2b_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        E2BHost,
        priority=E2B_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["E2B_PRIORITY", "PLUGIN_ID", "E2BHost", "register_e2b_contrib"]
