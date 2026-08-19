"""Load installed plugins from cache into an ExtensionRegistry (fail closed)."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from ageval.plugins.host_requires import installed_plugin
from ageval.plugins.manifest import PluginManifest, PluginManifestError, load_manifest
from ageval.plugins.plugin_requires import PluginRequiresError, assert_no_plugin_requires_cycle
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import get_slot_kind
from ageval.plugins.store import list_installed, resolve_package_root


class PluginLoadError(Exception):
    def __init__(self, message: str, *, kind: str = "plugin_load_failed") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _import_entry(package_root: Path, entry: str, extra_roots: Sequence[Path] = ()) -> Any:
    """Load ``module:attr`` with required neighbors then *package_root* on sys.path."""
    if ":" not in entry:
        raise PluginLoadError(f"bad entry {entry!r}", kind="plugin_entry_invalid")
    mod_name, attr = entry.split(":", 1)
    added: list[str] = []
    roots: list[Path] = []
    for extra in extra_roots:
        roots.extend((extra, extra / "src"))
    roots.extend((package_root, package_root / "src"))
    for p in roots:
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


def _manifest_with_index_id(manifest: PluginManifest, plugin_id: str) -> PluginManifest:
    if manifest.plugin_id == plugin_id:
        return manifest
    return replace(manifest, plugin_id=plugin_id)


def _required_roots(manifest: PluginManifest) -> list[Path]:
    """Package roots of declared plugin_requires that are already cached."""
    try:
        assert_no_plugin_requires_cycle(manifest.plugin_id)
    except PluginRequiresError as exc:
        raise PluginLoadError(exc.message, kind=exc.kind) from exc
    roots: list[Path] = []
    for item in manifest.plugin_requires:
        found = installed_plugin(item.plugin_id)
        if found is None:
            continue
        roots.append(found[1])
    return roots


def register_manifest(
    registry: ExtensionRegistry,
    manifest: Any,
    *,
    package_root: Path,
    digest: str | None = None,
    source: str = "installed",
) -> None:
    """Register all provide/on entries from a loaded manifest."""
    extra_roots = _required_roots(manifest)
    for slot_entry in manifest.provide:
        kind = get_slot_kind(slot_entry.id)
        if kind.value != "provide":
            raise PluginLoadError(
                f"slot {slot_entry.id!r} is multi; cannot provide()",
                kind="plugin_slot_kind_mismatch",
            )
        factory = _import_entry(package_root, slot_entry.entry, extra_roots)
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
        handler = _import_entry(package_root, slot_entry.entry, extra_roots)
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
        # Index id wins (Hub install stores org/name; path install keeps short id).
        register_manifest(
            registry,
            _manifest_with_index_id(manifest, entry.plugin_id),
            package_root=root,
            digest=entry.digest,
            source="installed",
        )
        loaded.append(entry.plugin_id)
    return loaded
