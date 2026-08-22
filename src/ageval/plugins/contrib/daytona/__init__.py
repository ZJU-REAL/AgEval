"""daytona box: the Attempt runs in a managed sandbox built from an OCI snapshot."""

from __future__ import annotations

from ageval.plugins.contrib.daytona.host import DaytonaHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "daytona"
DAYTONA_PRIORITY = 100


def register_daytona_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        DaytonaHost,
        priority=DAYTONA_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["DAYTONA_PRIORITY", "PLUGIN_ID", "DaytonaHost", "register_daytona_contrib"]
