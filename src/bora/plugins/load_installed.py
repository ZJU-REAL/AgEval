"""Load installed plugins from cache into an ExtensionRegistry (fail closed)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from bora.plugins.manifest import PluginManifestError, load_manifest
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import get_slot_kind
from bora.plugins.store import list_installed, resolve_package_root


class PluginLoadError(Exception):
    def __init__(self, message: str, *, kind: str = "plugin_load_failed") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _import_entry(package_root: Path, entry: str) -> Any:
    """Load ``module:attr`` with *package_root* (and package_root/src) on sys.path."""
    if ":" not in entry:
        raise PluginLoadError(f"bad entry {entry!r}", kind="plugin_entry_invalid")
    mod_name, attr = entry.split(":", 1)
    added: list[str] = []
    for p in (package_root, package_root / "src"):
        s = str(p.resolve(strict=False))
        if p.is_dir() and s not in sys.path:
            sys.path.insert(0, s)
            added.append(s)
    try:
        mod = importlib.import_module(mod_name)
        obj = getattr(mod, attr, None)
        if obj is None:
            raise PluginLoadError(
                f"entry attr missing: {entry}",
                kind="plugin_entry_missing",
            )
        return obj
    except PluginLoadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PluginLoadError(f"import failed for {entry}: {exc}") from exc


def register_manifest(
    registry: ExtensionRegistry,
    manifest: Any,
    *,
    package_root: Path,
    digest: str | None = None,
    source: str = "installed",
) -> None:
    """Register all provide/on entries from a loaded manifest."""
    for slot_entry in manifest.provide:
        kind = get_slot_kind(slot_entry.id)
        if kind.value != "provide":
            raise PluginLoadError(
                f"slot {slot_entry.id!r} is multi; cannot provide()",
                kind="plugin_slot_kind_mismatch",
            )
        factory = _import_entry(package_root, slot_entry.entry)
        registry.provide(
            slot_entry.id,
            manifest.plugin_id,
            factory,
            priority=slot_entry.priority,
            source=source,
            version=manifest.version,
            digest=digest,
            is_factory=True,
        )
    for slot_entry in manifest.on:
        kind = get_slot_kind(slot_entry.id)
        if kind.value != "multi":
            raise PluginLoadError(
                f"slot {slot_entry.id!r} is provide; cannot on()",
                kind="plugin_slot_kind_mismatch",
            )
        handler = _import_entry(package_root, slot_entry.entry)
        registry.on(
            slot_entry.id,
            manifest.plugin_id,
            handler,
            priority=slot_entry.priority,
            source=source,
            version=manifest.version,
            digest=digest,
            is_factory=False,
        )


def load_installed_plugins(registry: ExtensionRegistry) -> list[str]:
    """Load every index entry into *registry*. Fail closed on any bad package."""
    loaded: list[str] = []
    for entry in list_installed():
        root = resolve_package_root(entry)
        if not root.is_dir():
            raise PluginLoadError(
                f"installed plugin path missing: {root}",
                kind="plugin_path_missing",
            )
        try:
            manifest = load_manifest(root)
        except PluginManifestError as exc:
            raise PluginLoadError(str(exc), kind=exc.kind) from exc
        register_manifest(
            registry,
            manifest,
            package_root=root,
            digest=entry.digest,
            source="installed",
        )
        loaded.append(entry.plugin_id)
    return loaded
