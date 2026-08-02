"""Production composition root.

All concrete adapters and use cases that the public CLI needs must be assembled
here. Domain modules (config, future runtime) must not construct global
singletons at import time.
"""

from __future__ import annotations

from bora.adapters.package_fs import LocalPackageReader
from bora.application.lock_command import LockCommand
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore


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
