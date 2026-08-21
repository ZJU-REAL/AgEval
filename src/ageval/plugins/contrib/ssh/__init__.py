"""ssh box: the Attempt runs on a remote machine, or in a container on it."""

from __future__ import annotations

from ageval.plugins.contrib.ssh.host import SSHHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "ssh"
SSH_PRIORITY = 100


def register_ssh_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        SSHHost,
        priority=SSH_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "SSH_PRIORITY", "SSHHost", "register_ssh_contrib"]
