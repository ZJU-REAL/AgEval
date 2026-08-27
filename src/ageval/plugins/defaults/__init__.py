"""Engine default contributions.

Chain: recognize ``environment/setup.sh``.
Exclusive: parent evaluator launch and layer-C trajectory write.

There is deliberately no pass-through handler registered on every chain —
an empty chain already means "nothing to do", and filling the lock with no-op
rows hides which plugin actually acts.
"""

from __future__ import annotations

from ageval.plugins.defaults.environment_setup import (
    SETUP_PRIORITY,
    default_environment_setup,
)
from ageval.plugins.defaults.evaluation_runtime import build_evaluation_runtime
from ageval.plugins.defaults.trajectory_seal import build_trajectory_seal
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT_SETUP, EVALUATION_RUNTIME, TRAJECTORY_SEAL

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
    registry.exclusive(
        EVALUATION_RUNTIME,
        PLUGIN_ID,
        build_evaluation_runtime,
        source="default",
        is_default=True,
        is_factory=True,
    )
    registry.exclusive(
        TRAJECTORY_SEAL,
        PLUGIN_ID,
        build_trajectory_seal,
        source="default",
        is_default=True,
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "register_defaults"]
