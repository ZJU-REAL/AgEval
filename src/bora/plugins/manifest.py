"""Parse and validate ``bora.plugin/1`` manifests (plugin.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PLUGIN_FORMAT = "bora.plugin/1"
MANIFEST_NAMES = ("plugin.yaml", "bora.plugin.yaml")


class PluginManifestError(Exception):
    """Invalid plugin package / manifest."""

    def __init__(self, message: str, *, kind: str = "invalid_plugin_manifest") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class SlotEntry:
    id: str
    priority: int
    entry: str  # module:attr


@dataclass(frozen=True, slots=True)
class PluginManifest:
    format: str
    plugin_id: str
    version: str
    provide: tuple[SlotEntry, ...] = ()
    on: tuple[SlotEntry, ...] = ()
    source_path: str | None = None

    def slots_summary(self) -> dict[str, list[str]]:
        return {
            "provide": [s.id for s in self.provide],
            "on": [s.id for s in self.on],
        }


def find_manifest_file(root: Path) -> Path:
    for name in MANIFEST_NAMES:
        p = root / name
        if p.is_file():
            return p
    raise PluginManifestError(
        f"no plugin.yaml in {root}",
        kind="plugin_manifest_missing",
    )


def parse_manifest_mapping(raw: dict[str, Any], *, location: str = "plugin.yaml") -> PluginManifest:
    fmt = raw.get("format")
    if fmt != PLUGIN_FORMAT:
        raise PluginManifestError(
            f"unsupported plugin format: {fmt!r} (want {PLUGIN_FORMAT})",
            kind="plugin_format_invalid",
        )
    plugin_id = raw.get("plugin_id")
    version = raw.get("version")
    if not isinstance(plugin_id, str) or not plugin_id.strip():
        raise PluginManifestError("plugin_id required", kind="plugin_manifest_invalid")
    if not isinstance(version, str) or not version.strip():
        raise PluginManifestError("version required", kind="plugin_manifest_invalid")

    slots = raw.get("slots")
    if slots is None:
        slots = {}
    if not isinstance(slots, dict):
        raise PluginManifestError("slots must be a mapping", kind="plugin_manifest_invalid")

    def _entries(key: str) -> tuple[SlotEntry, ...]:
        rows = slots.get(key) or []
        if not isinstance(rows, list):
            raise PluginManifestError(f"slots.{key} must be a list", kind="plugin_manifest_invalid")
        out: list[SlotEntry] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise PluginManifestError(
                    f"slots.{key}[{i}] must be a mapping",
                    kind="plugin_manifest_invalid",
                )
            sid = row.get("id")
            entry = row.get("entry")
            if not isinstance(sid, str) or not sid.strip():
                raise PluginManifestError(
                    f"slots.{key}[{i}].id required",
                    kind="plugin_manifest_invalid",
                )
            if not isinstance(entry, str) or ":" not in entry:
                raise PluginManifestError(
                    f"slots.{key}[{i}].entry must be module:attr",
                    kind="plugin_manifest_invalid",
                )
            prio = row.get("priority", 100)
            try:
                priority = int(prio)
            except (TypeError, ValueError) as exc:
                raise PluginManifestError(
                    f"slots.{key}[{i}].priority invalid",
                    kind="plugin_manifest_invalid",
                ) from exc
            out.append(SlotEntry(id=sid.strip(), priority=priority, entry=entry.strip()))
        return tuple(out)

    return PluginManifest(
        format=PLUGIN_FORMAT,
        plugin_id=plugin_id.strip(),
        version=version.strip(),
        provide=_entries("provide"),
        on=_entries("on"),
        source_path=location,
    )


def load_manifest(root: Path) -> PluginManifest:
    path = find_manifest_file(root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PluginManifestError(f"cannot read {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PluginManifestError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginManifestError("manifest root must be a mapping")
    return parse_manifest_mapping(data, location=str(path))
