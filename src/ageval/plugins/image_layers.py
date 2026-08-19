"""Dockerfile fragments installed plugins contribute to an Attempt image.

A layer list is not a slot. Nothing runs at a point in the timeline here: the
environment winner reads what the bound plugins declared and folds it into the
image it builds. That is why ``image_contribute`` left the timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ageval.plugins.manifest import PluginManifest, load_manifest
from ageval.plugins.store import list_installed, resolve_package_root


@dataclass(frozen=True, slots=True)
class ImageLayer:
    """One plugin's Dockerfile fragment, already read from its package."""

    plugin_id: str
    body: str


def layers_for_plugins(plugin_ids: frozenset[str]) -> tuple[ImageLayer, ...]:
    """Fragments declared by the installed plugins among *plugin_ids*.

    Ordered by plugin id so the image key does not depend on resolve order.
    """
    found: list[ImageLayer] = []
    for entry in list_installed():
        if entry.plugin_id not in plugin_ids:
            continue
        root = resolve_package_root(entry)
        manifest = _manifest(root)
        if manifest is None or manifest.image_layers is None:
            continue
        fragment = root / manifest.image_layers
        if not fragment.is_file():
            continue
        found.append(ImageLayer(plugin_id=entry.plugin_id, body=fragment.read_text("utf-8")))
    return tuple(sorted(found, key=lambda layer: layer.plugin_id))


def _manifest(root: Path) -> PluginManifest | None:
    from ageval.plugins.manifest import PluginManifestError

    try:
        return load_manifest(root)
    except PluginManifestError:
        # A broken install is reported where it is installed, not here.
        return None
