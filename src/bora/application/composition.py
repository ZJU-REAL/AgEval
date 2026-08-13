"""Production composition root.

All concrete adapters and use cases that the public CLI needs must be assembled
here. Domain modules (config, future runtime) must not construct global
singletons at import time.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from bora.adapters.package_fs import LocalPackageReader
from bora.application.attempt.lock_command import LockCommand
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore
from bora.evaluation.result_binding import FlatResult

# Public use-case type: one foreground Attempt.
RunTask = Callable[..., Coroutine[Any, Any, tuple[int, FlatResult, dict[str, Any]]]]


def build_config_core() -> ConfigCore:
    """Assemble Config Core with the production package reader."""
    return ConfigCore(package_reader=LocalPackageReader())


def build_declaration_catalog() -> DeclarationCapabilityCatalog:
    """Return the declaration-only catalog used at lock time.

    A positive catalog answer means "Config recognizes this declaration",
    never "the runtime adapter is implemented and ready".
    """
    return DeclarationCapabilityCatalog()


def build_lock_command() -> LockCommand:
    """Wire the production ``bora lock`` use case."""
    return LockCommand(
        config_core=build_config_core(),
        capabilities=build_declaration_catalog(),
    )


def build_run_task() -> RunTask:
    """Wire the production ``bora run`` use case through the composition root.

    Concrete adapters remain inside the use case module for now; the CLI must
    not import ``run_command.run_task`` directly. Full lifecycle/authority
    assembly is still residual vs Spec 05 text.
    """
    from bora.application.attempt.run_command import run_task

    return run_task


def build_campaign_runner() -> Callable[..., Coroutine[Any, Any, dict[str, Any]]]:
    """Wire the production ``bora campaign`` sketch through the composition root."""
    from bora.application.attempt.campaign import run_campaign

    return run_campaign


def build_suite_runner() -> Any:
    """Suite plan / execute / cancel / locator helpers."""
    from bora.application.suite import suite_run

    return suite_run


def build_results_commands() -> Any:
    """Attempt and suite result upload / get / list / share / delete."""
    from bora.application.registry_ops import results_command

    return results_command


def build_registry_list_commands() -> Any:
    """Package list/show/delete/visibility and local cache helpers."""
    from bora.application.registry_ops import registry_list_command

    return registry_list_command


def build_registry_org_commands() -> Any:
    """Org create / list."""
    from bora.application.registry_ops import registry_org_command

    return registry_org_command


def build_publish_command() -> Any:
    from bora.application.registry_ops import publish_command

    return publish_command


def build_login_command() -> Any:
    from bora.application.registry_ops import login_command

    return login_command


def build_plugin_commands() -> Any:
    from bora.application.plugin_ops import plugin_install_remote, plugin_publish

    return type(
        "PluginCommands",
        (),
        {
            "install_plugin_from_registry": staticmethod(
                plugin_install_remote.install_plugin_from_registry
            ),
            "publish_plugin": staticmethod(plugin_publish.publish_plugin),
        },
    )()


def build_registry_client(
    *,
    registry_url: str | None = None,
    require_token: bool = True,
    accept_results_url: bool = False,
) -> Any:
    from bora.application.registry_ops.client import build_registry_client as _build

    return _build(
        registry_url=registry_url,
        require_token=require_token,
        accept_results_url=accept_results_url,
    )
