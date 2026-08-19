"""Stable error kinds for the extension registry / resolve path."""

from __future__ import annotations


class ExtensionRegistryError(Exception):
    """Base for extension registry failures (fail closed)."""

    kind: str = "extension_registry_error"

    def __init__(self, message: str, *, kind: str | None = None) -> None:
        super().__init__(message)
        if kind is not None:
            self.kind = kind
        self.message = message


class UnknownExtensionSlotError(ExtensionRegistryError):
    kind = "unknown_extension_slot"


class ExtensionPluginNotFoundError(ExtensionRegistryError):
    kind = "extension_plugin_not_found"


class ExtensionMaterializeError(ExtensionRegistryError):
    kind = "extension_materialize_failed"
