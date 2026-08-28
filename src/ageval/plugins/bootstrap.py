"""Composition-root bootstrap for the extension registry.

Order: engine defaults → first-party contribs → installed plugin cache.
Ecosystem plugins load only after ``ageval plugin install``.
"""

from __future__ import annotations

from ageval.plugins.contrib.acp import register_acp_contrib
from ageval.plugins.contrib.anthropic_http import register_anthropic_http_contrib
from ageval.plugins.contrib.daytona import register_daytona_contrib
from ageval.plugins.contrib.docker import register_docker_contrib
from ageval.plugins.contrib.e2b import register_e2b_contrib
from ageval.plugins.contrib.local import register_local_contrib
from ageval.plugins.contrib.openai_http import register_openai_http_contrib
from ageval.plugins.contrib.ssh import register_ssh_contrib
from ageval.plugins.defaults import register_defaults
from ageval.plugins.registry import ExtensionRegistry, get_global_registry, reset_global_registry

_BOOTSTRAPPED = False


def bootstrap_registry(
    registry: ExtensionRegistry | None = None,
    *,
    force: bool = False,
) -> ExtensionRegistry:
    """Ensure the process registry has engine + first-party contributions."""
    global _BOOTSTRAPPED
    reg = registry if registry is not None else get_global_registry()
    if registry is None and _BOOTSTRAPPED and not force:
        return reg
    if force and registry is None:
        reg = reset_global_registry()
    elif force and registry is not None:
        reg.clear()

    register_defaults(reg)
    register_local_contrib(reg)
    register_docker_contrib(reg)
    register_e2b_contrib(reg)
    register_daytona_contrib(reg)
    register_ssh_contrib(reg)
    register_acp_contrib(reg)
    register_openai_http_contrib(reg)
    register_anthropic_http_contrib(reg)

    from ageval.plugins.load_installed import load_installed_plugins

    load_installed_plugins(reg)

    if registry is None:
        _BOOTSTRAPPED = True
    return reg


def ensure_bootstrapped() -> ExtensionRegistry:
    return bootstrap_registry()
