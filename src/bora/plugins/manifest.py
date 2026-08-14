"""Parse and validate ``bora.plugin/1`` manifests (plugin.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PLUGIN_FORMAT = "bora.plugin/1"
MANIFEST_NAMES = ("plugin.yaml", "bora.plugin.yaml")
# Default Hub official-org allowlist. Runtime lock/run never consults this.
DEFAULT_OFFICIAL_ORG = "Official"
# Same slash form as Dataset database_id. Not org.name. Official is mixed-case.
_PLUGIN_ID_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")


class PluginManifestError(Exception):
    """Invalid plugin package / manifest."""

    def __init__(self, message: str, *, kind: str = "invalid_plugin_manifest") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def split_plugin_id(plugin_id: str) -> tuple[str | None, str]:
    """Return ``(org, name)`` for ``org/name``, or ``(None, short_id)``."""
    if "/" not in plugin_id:
        return None, plugin_id
    org, name = plugin_id.split("/", 1)
    return org, name


def normalize_plugin_id(raw: str) -> str:
    """Validate short ``name`` or Hub ``org/name``. Reject ``org.name``."""
    plugin_id = raw.strip()
    if not plugin_id:
        raise PluginManifestError("plugin_id required", kind="plugin_manifest_invalid")
    if plugin_id.count("/") > 1:
        raise PluginManifestError(
            f"plugin_id must be name or org/name, not {plugin_id!r}",
            kind="plugin_id_invalid",
        )
    org, name = split_plugin_id(plugin_id)
    parts = (org, name) if org is not None else (name,)
    if any(p is None or not _PLUGIN_ID_SEGMENT.fullmatch(p) for p in parts):
        raise PluginManifestError(
            f"plugin_id must be name or org/name, not {plugin_id!r}",
            kind="plugin_id_invalid",
        )
    return plugin_id


def hub_plugin_package_id(plugin_id: str, *, org: str) -> str:
    """Hub address for publish: short id concatenates; namespaced must match *org*."""
    org_id = org.strip()
    if not org_id:
        raise PluginManifestError("org required", kind="plugin_org_required")
    prefix, name = split_plugin_id(plugin_id)
    if prefix is None:
        if not name:
            raise PluginManifestError("plugin_id required", kind="plugin_manifest_invalid")
        return f"{org_id}/{name}"
    if prefix != org_id:
        raise PluginManifestError(
            f"plugin_id prefix {prefix!r} does not match upload org {org_id!r}",
            kind="plugin_org_mismatch",
        )
    return plugin_id


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
    plugin_id = normalize_plugin_id(plugin_id)
    if not isinstance(version, str) or not version.strip():
        raise PluginManifestError("version required", kind="plugin_manifest_invalid")

    slots = raw.get("slots")
    if slots is None:
        slots = {}
    if not isinstance(slots, dict):
        raise PluginManifestError("slots must be a mapping", kind="plugin_manifest_invalid")

    def _entries(key: str) -> tuple[SlotEntry, ...]:
        # PyYAML 1.1 may coerce bare mapping key ``on:`` to boolean True.
        rows = slots.get(key)
        if rows is None and key == "on":
            rows = slots.get(True)
        rows = rows or []
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
        plugin_id=plugin_id,
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
