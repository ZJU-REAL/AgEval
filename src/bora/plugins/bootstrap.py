"""Composition-root bootstrap for the extension registry.

MVP: always register defaults + first-party acp/nooa. No soft-import glue.
"""

from __future__ import annotations

from bora.plugins.contrib.acp import register_acp_contrib
from bora.plugins.contrib.mock import register_mock_contrib
from bora.plugins.contrib.nooa import register_nooa_contrib
from bora.plugins.contrib.openai_http import register_openai_http_contrib
from bora.plugins.defaults import register_defaults
from bora.plugins.registry import ExtensionRegistry, get_global_registry, reset_global_registry

_BOOTSTRAPPED = False


def bootstrap_registry(
    registry: ExtensionRegistry | None = None,
    *,
    force: bool = False,
    include_acp: bool = True,
    include_nooa: bool = True,
    include_openai_http: bool = True,
    include_mock: bool = True,
) -> ExtensionRegistry:
    """Ensure the process registry has builtin + first-party contributions."""
    global _BOOTSTRAPPED
    reg = registry if registry is not None else get_global_registry()
    if registry is None and _BOOTSTRAPPED and not force:
        return reg
    if force and registry is None:
        reg = reset_global_registry()
    elif force and registry is not None:
        reg.clear()

    register_defaults(reg)
    if include_acp:
        register_acp_contrib(reg)
    if include_nooa:
        register_nooa_contrib(reg)
    if include_openai_http:
        register_openai_http_contrib(reg)
    if include_mock:
        register_mock_contrib(reg)

    if registry is None:
        _BOOTSTRAPPED = True
    return reg


def ensure_bootstrapped() -> ExtensionRegistry:
    return bootstrap_registry()
