"""docker box: the Attempt runs in a container built from the task's own recipe.

Registered as an ``environment`` exclusive-slot candidate. Nothing above this
package learns a container id — that is the point of the slot.
"""

from __future__ import annotations

from ageval.plugins.contrib.docker.host import DockerHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "docker"
DOCKER_PRIORITY = 100


def register_docker_contrib(registry: ExtensionRegistry) -> None:
    # The class is the factory, so its capabilities are readable at lock time.
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        DockerHost,
        priority=DOCKER_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["DOCKER_PRIORITY", "PLUGIN_ID", "DockerHost", "register_docker_contrib"]
