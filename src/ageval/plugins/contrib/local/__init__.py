"""Local box: the Attempt runs in a real directory tree on this machine.

``local`` is a production kind, not a test double. It owns a work root, maps the
in-box path contract onto real directories, execs real subprocesses, and hands
ACP a real ``Popen`` pipe.
"""

from __future__ import annotations

from ageval.plugins.contrib.local.host import LocalHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "local"
LOCAL_PRIORITY = 100


def register_local_contrib(registry: ExtensionRegistry) -> None:
    # The class is the factory, so its declared capabilities are readable at
    # lock time — before any box exists.
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        LocalHost,
        priority=LOCAL_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["LOCAL_PRIORITY", "PLUGIN_ID", "LocalHost", "register_local_contrib"]
