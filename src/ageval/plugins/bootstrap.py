"""Composition-root bootstrap for the extension registry.

First-party: defaults + ACP (+ optional openai-http / mock).
Ecosystem plugins (e.g. nooa) load only via ``load_installed_plugins`` after
``ageval plugin install`` — never registered by default here.
"""

from __future__ import annotations

from ageval.plugins.contrib.acp import register_acp_contrib
from ageval.plugins.contrib.mock import register_mock_contrib
from ageval.plugins.contrib.openai_http import register_openai_http_contrib
from ageval.plugins.defaults import register_defaults
from ageval.plugins.registry import ExtensionRegistry, get_global_registry, reset_global_registry

_BOOTSTRAPPED = False


def bootstrap_registry(
    registry: ExtensionRegistry | None = None,
    *,
    force: bool = False,
    include_acp: bool = True,
    include_openai_http: bool = True,
    include_mock: bool = True,
) -> ExtensionRegistry:
    """Ensure the process registry has builtin + first-party contributions.

    Installed cache plugins are loaded after first-party (fail closed on bad pkg).
    """
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
    if include_openai_http:
        register_openai_http_contrib(reg)
    if include_mock:
        register_mock_contrib(reg)

    # Spec 03: installed cache plugins after first-party (fail closed on bad pkg).
    from ageval.plugins.load_installed import load_installed_plugins

    load_installed_plugins(reg)

    if registry is None:
        _BOOTSTRAPPED = True
    return reg


def ensure_bootstrapped() -> ExtensionRegistry:
    return bootstrap_registry()
