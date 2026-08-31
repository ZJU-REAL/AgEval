"""Dockerfile fragments installed plugins contribute to an Attempt image.

A layer list is not a slot. Nothing runs at a point in the timeline here: the
environment winner reads what the bound plugins declared and folds it into the
image it builds. That is why ``image_contribute`` left the timeline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ageval.plugins.manifest import PluginManifest, load_manifest
from ageval.plugins.store import load_index, resolve_package_root

if TYPE_CHECKING:
    from ageval.plugins.protocol import ExtensionGraph


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


def graph_plugin_ids(graph: ExtensionGraph) -> frozenset[str]:
    """Plugin ids a graph binds: exclusive winners plus every chain handler."""
    bound = {ref.plugin_id for ref in graph.winners.values()}
    for chain in graph.chains.values():
        bound.update(handler.plugin_id for handler in chain)
    return frozenset(bound)


def layers_tuple(layers: Iterable[ImageLayer]) -> tuple[tuple[str, str, str, str], ...]:
    """The factory-facing layer shape (plugin_id, dockerfile, package_root, body)."""
    return tuple(
        (layer.plugin_id, str(layer.dockerfile), str(layer.package_root), layer.body)
        for layer in layers
    )


def layers_for_graph(graph: ExtensionGraph) -> tuple[tuple[str, str, str, str], ...]:
    """Bake files declared by the plugins one graph binds, for kinds that build."""
    return layers_tuple(layers_for_plugins(graph_plugin_ids(graph)))


def layers_for_graphs(
    graphs: Iterable[ExtensionGraph],
) -> tuple[tuple[str, str, str, str], ...]:
    """Union bake files over several graphs, ordered by plugin id."""
    bound: set[str] = set()
    for graph in graphs:
        bound.update(graph_plugin_ids(graph))
    return layers_tuple(layers_for_plugins(frozenset(bound)))
