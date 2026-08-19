"""Local box: the Attempt runs in a real directory tree on this machine.

``local`` is a production kind, not a test double. It owns a work root, maps the
in-box path contract onto real directories, execs real subprocesses, and hands
ACP a real ``Popen`` pipe.
"""

from __future__ import annotations

from typing import Any

from ageval.plugins.contrib.local.host import LocalHost
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import ENVIRONMENT

PLUGIN_ID = "local"
LOCAL_PRIORITY = 100


def _local_factory(**kwargs: Any) -> LocalHost:
    return LocalHost(
        options=dict(kwargs.get("options") or {}),
        attempt_root=kwargs.get("attempt_root"),
    )


def register_local_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        ENVIRONMENT,
        PLUGIN_ID,
        _local_factory,
        priority=LOCAL_PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["LOCAL_PRIORITY", "PLUGIN_ID", "LocalHost", "register_local_contrib"]
