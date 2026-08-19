"""Parse and validate ``ageval.plugin/1`` manifests (plugin.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PLUGIN_FORMAT = "ageval.plugin/1"
MANIFEST_NAMES = ("plugin.yaml", "ageval.plugin.yaml")
# Default Hub official-org allowlist (org slug). Runtime lock/run never consults this.
DEFAULT_OFFICIAL_ORG = "official"
# Same slash form as Dataset dataset_id. Not org.name. Official is mixed-case.
_PLUGIN_ID_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
HOST_REQUIRES_KEYS = frozenset({"import", "file", "hint"})
PLUGIN_REQUIRES_KEYS = frozenset({"plugin_id", "hint"})


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
class HostRequire:
    """One declared L0 host prerequisite. Core executes this list only."""

    import_name: str | None = None
    file: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class PluginRequire:
    """One declared plugin-cache dependency. Not a host extra."""

    plugin_id: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceExport:
    """One ``exports.services`` row (extra named capability)."""

    id: str
    entry: str


@dataclass(frozen=True, slots=True)
class InjectRow:
    """One ``inject`` row: service name plus the capabilities it will call."""

    service: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PluginManifest:
    format: str
    plugin_id: str
    version: str
    exclusive: tuple[SlotEntry, ...] = ()
    chain: tuple[SlotEntry, ...] = ()
    services: tuple[ServiceExport, ...] = ()
    inject: tuple[InjectRow, ...] = ()
    host_requires: tuple[HostRequire, ...] = ()
    plugin_requires: tuple[PluginRequire, ...] = ()
    source_path: str | None = None

    def slots_summary(self) -> dict[str, list[str]]:
        return {
            "exclusive": [s.id for s in self.exclusive],
            "chain": [s.id for s in self.chain],
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

    unknown_slot_keys = sorted(str(k) for k in slots if str(k) not in {"exclusive", "chain"})
    if unknown_slot_keys:
        raise PluginManifestError(
            f"unknown slots keys: {unknown_slot_keys} (expected exclusive / chain)",
            kind="plugin_manifest_invalid",
        )

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
        plugin_id=plugin_id,
        version=version.strip(),
        exclusive=_entries("exclusive"),
        chain=_entries("chain"),
        services=_parse_services(raw.get("exports")),
        inject=_parse_inject(raw.get("inject")),
        host_requires=_parse_host_requires(raw.get("host_requires")),
        plugin_requires=_parse_plugin_requires(raw.get("plugin_requires")),
        source_path=location,
    )


def _parse_services(raw: Any) -> tuple[ServiceExport, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise PluginManifestError("exports must be a mapping", kind="plugin_manifest_invalid")
    unknown = sorted(str(k) for k in raw if str(k) != "services")
    if unknown:
        raise PluginManifestError(
            f"unknown exports keys: {unknown}", kind="plugin_manifest_invalid"
        )
    rows = raw.get("services") or []
    if not isinstance(rows, list):
        raise PluginManifestError("exports.services must be a list", kind="plugin_manifest_invalid")
    out: list[ServiceExport] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PluginManifestError(
                f"exports.services[{i}] must be a mapping", kind="plugin_manifest_invalid"
            )
        sid = row.get("id")
        entry = row.get("entry")
        if not isinstance(sid, str) or not sid.strip():
            raise PluginManifestError(
                f"exports.services[{i}].id required", kind="plugin_manifest_invalid"
            )
        if not isinstance(entry, str) or ":" not in entry:
            raise PluginManifestError(
                f"exports.services[{i}].entry must be module:attr",
                kind="plugin_manifest_invalid",
            )
        out.append(ServiceExport(id=sid.strip(), entry=entry.strip()))
    return tuple(out)


def _parse_inject(raw: Any) -> tuple[InjectRow, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PluginManifestError("inject must be a list", kind="plugin_manifest_invalid")
    out: list[InjectRow] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise PluginManifestError(
                f"inject[{i}] must be a mapping", kind="plugin_manifest_invalid"
            )
        unknown = sorted(str(k) for k in row if str(k) not in {"service", "capabilities"})
        if unknown:
            raise PluginManifestError(
                f"inject[{i}] unknown keys: {unknown}", kind="plugin_manifest_invalid"
            )
        service = row.get("service")
        if not isinstance(service, str) or not service.strip():
            raise PluginManifestError(
                f"inject[{i}].service required", kind="plugin_manifest_invalid"
            )
        caps_raw = row.get("capabilities") or []
        if not isinstance(caps_raw, list):
            raise PluginManifestError(
                f"inject[{i}].capabilities must be a list", kind="plugin_manifest_invalid"
            )
        out.append(
            InjectRow(
                service=service.strip(),
                capabilities=tuple(str(c).strip() for c in caps_raw if str(c).strip()),
            )
        )
    return tuple(out)


def _parse_host_requires(raw: Any) -> tuple[HostRequire, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PluginManifestError(
            "host_requires must be a list",
            kind="plugin_host_requires_invalid",
        )
    out: list[HostRequire] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise PluginManifestError(
                f"host_requires[{i}] must be a mapping",
                kind="plugin_host_requires_invalid",
            )
        unknown = sorted(str(k) for k in row if str(k) not in HOST_REQUIRES_KEYS)
        if unknown:
            raise PluginManifestError(
                f"host_requires[{i}] unknown keys: {unknown}",
                kind="plugin_host_requires_invalid",
            )
        import_name = row.get("import")
        file_rel = row.get("file")
        hint = row.get("hint")
        if import_name is not None and (
            not isinstance(import_name, str) or not import_name.strip()
        ):
            raise PluginManifestError(
                f"host_requires[{i}].import must be a non-empty string",
                kind="plugin_host_requires_invalid",
            )
        if file_rel is not None and (not isinstance(file_rel, str) or not file_rel.strip()):
            raise PluginManifestError(
                f"host_requires[{i}].file must be a non-empty string",
                kind="plugin_host_requires_invalid",
            )
        if hint is not None and (not isinstance(hint, str) or not hint.strip()):
            raise PluginManifestError(
                f"host_requires[{i}].hint must be a non-empty string",
                kind="plugin_host_requires_invalid",
            )
        imp = import_name.strip() if isinstance(import_name, str) else None
        file_s = file_rel.strip() if isinstance(file_rel, str) else None
        hint_s = hint.strip() if isinstance(hint, str) else None
        if not imp and not file_s:
            raise PluginManifestError(
                f"host_requires[{i}] must declare import and/or file",
                kind="plugin_host_requires_invalid",
            )
        out.append(HostRequire(import_name=imp, file=file_s, hint=hint_s))
    return tuple(out)


def _parse_plugin_requires(raw: Any) -> tuple[PluginRequire, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PluginManifestError(
            "plugin_requires must be a list",
            kind="plugin_requires_invalid",
        )
    out: list[PluginRequire] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise PluginManifestError(
                f"plugin_requires[{i}] must be a mapping",
                kind="plugin_requires_invalid",
            )
        unknown = sorted(str(k) for k in row if str(k) not in PLUGIN_REQUIRES_KEYS)
        if unknown:
            raise PluginManifestError(
                f"plugin_requires[{i}] unknown keys: {unknown}",
                kind="plugin_requires_invalid",
            )
        plugin_id = row.get("plugin_id")
        hint = row.get("hint")
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            raise PluginManifestError(
                f"plugin_requires[{i}].plugin_id required",
                kind="plugin_requires_invalid",
            )
        try:
            normalized = normalize_plugin_id(plugin_id)
        except PluginManifestError as exc:
            raise PluginManifestError(
                f"plugin_requires[{i}].plugin_id invalid: {exc.message}",
                kind="plugin_requires_invalid",
            ) from exc
        if hint is not None and (not isinstance(hint, str) or not hint.strip()):
            raise PluginManifestError(
                f"plugin_requires[{i}].hint must be a non-empty string",
                kind="plugin_requires_invalid",
            )
        hint_s = hint.strip() if isinstance(hint, str) else None
        out.append(PluginRequire(plugin_id=normalized, hint=hint_s))
    return tuple(out)


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
