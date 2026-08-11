"""Composition-root bootstrap for the extension registry.

Registers defaults (Spec 00). Optional first-party contribs (ACP Spec 01,
nooa Spec 02) when packages are present. Hub-installed plugins are Spec 03.
"""

from __future__ import annotations

from bora.plugins.defaults import register_defaults
from bora.plugins.registry import ExtensionRegistry, get_global_registry, reset_global_registry

_BOOTSTRAPPED = False


def bootstrap_registry(
    registry: ExtensionRegistry | None = None,
    *,
    force: bool = False,
    include_acp: bool = True,
    include_nooa: bool = True,
) -> ExtensionRegistry:
    """Ensure the process registry has builtin + available first-party contribs."""
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
        try:
            from bora.plugins.contrib.acp import register_acp_contrib
        except ImportError:
            pass
        else:
            register_acp_contrib(reg)
    if include_nooa:
        try:
            from bora.plugins.contrib.nooa import register_nooa_contrib
        except ImportError:
            pass
        else:
            register_nooa_contrib(reg)

    if registry is None:
        _BOOTSTRAPPED = True
    return reg


def ensure_bootstrapped() -> ExtensionRegistry:
    return bootstrap_registry()
