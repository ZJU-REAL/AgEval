"""Test helpers: build an ExtensionRegistry with a fake executor plugin."""

from __future__ import annotations

from typing import Any

from ageval.plugins.defaults import register_defaults
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR


def registry_with_executor(
    plugin_id: str,
    impl: Any,
    *,
    priority: int = 10,
    include_defaults: bool = True,
) -> ExtensionRegistry:
    """Register *impl* as provide(executor) for *plugin_id* (for unit tests)."""
    reg = ExtensionRegistry()
    if include_defaults:
        register_defaults(reg)
    reg.exclusive(
        EXECUTOR,
        plugin_id,
        impl,
        priority=priority,
        source="test",
        is_factory=False,
    )
    return reg
