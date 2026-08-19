"""Engine default contributions.

Only two things are defaults: recognizing ``environment/setup.sh`` and nothing
else. There is deliberately no pass-through handler registered on every chain —
an empty chain already means "nothing to do", and filling the lock with no-op
rows hides which plugin actually acts.
"""

from __future__ import annotations

from ageval.plugins.defaults.environment_setup import (
    SETUP_PRIORITY,
    default_environment_setup,
)
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT_SETUP

PLUGIN_ID = "default"


def register_defaults(registry: ExtensionRegistry) -> None:
    registry.chain(
        ENVIRONMENT_SETUP,
        PLUGIN_ID,
        default_environment_setup,
        priority=SETUP_PRIORITY,
        source="default",
        is_default=True,
    )


__all__ = ["PLUGIN_ID", "register_defaults"]
