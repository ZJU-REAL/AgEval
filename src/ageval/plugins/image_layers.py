"""Dockerfile fragments installed plugins contribute to an Attempt image.

A layer list is not a slot. Nothing runs at a point in the timeline here: the
environment winner reads what the bound plugins declared and folds it into the
image it builds. That is why ``image_contribute`` left the timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ageval.plugins.manifest import PluginManifest, load_manifest
from ageval.plugins.store import load_index, resolve_package_root


@dataclass(frozen=True, slots=True)
class ImageLayer:
    """One plugin's bake file, built with the plugin package as context."""

    plugin_id: str
    dockerfile: Path
    package_root: Path
    body: str


def layers_for_plugins(plugin_ids: frozenset[str]) -> tuple[ImageLayer, ...]:
    """Bake files declared by the installed plugins among *plugin_ids*.

    Ordered by plugin id so the image key does not depend on resolve order.
    """
    if not plugin_ids:
        return ()
    index = load_index()
    found: list[ImageLayer] = []
    for plugin_id in sorted(plugin_ids):
        entry = index.find(plugin_id)
        if entry is None:
            continue
        root = resolve_package_root(entry)
        manifest = _manifest(root)
        if manifest is None or manifest.image_layers is None:
            continue
        fragment = root / manifest.image_layers
        if not fragment.is_file():
            continue
        found.append(
            ImageLayer(
                plugin_id=entry.plugin_id,
                dockerfile=fragment,
                package_root=root,
                body=fragment.read_text("utf-8"),
            )
        )
    return tuple(found)


def _manifest(root: Path) -> PluginManifest | None:
    from ageval.plugins.manifest import PluginManifestError

    try:
        return load_manifest(root)
    except PluginManifestError:
        # A broken install is reported where it is installed, not here.
        return None
