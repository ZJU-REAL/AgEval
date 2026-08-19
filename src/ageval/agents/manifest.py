"""Parse and validate ``ageval.agent/1`` (``agent.yaml``) — design/14.

The ``binding`` block is exactly one ``ageval.profiles/1`` binding and is
validated by the same parser (key allowlist, options denylist, overlay path
shape). ``binding.agent_ref`` is reserved for the --agent projection and
rejected here. Every file in the package is secret-scanned fail-closed.
"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ageval.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ConfigError,
)
from ageval.config.overlay_files import (
    assert_overlays_at_lock,
    parse_overlay_paths,
    scan_overlay_files,
)
from ageval.config.profiles import PROFILES_FORMAT, parse_profiles_mapping

AGENT_FILENAME = "agent.yaml"
AGENT_FORMAT = "ageval.agent/1"

# Short id, or org/name Hub address (one slash), matching plugin id rules.
_AGENT_ID_RE = re.compile(r"^(?:[a-z0-9][a-z0-9_-]*/)?[a-z0-9][a-z0-9_-]*$")

_TOP_LEVEL_KEYS = frozenset(
    {"format", "agent_id", "version", "label", "description", "tags", "binding"}
)

# Placeholder role used only to run the profiles binding validator.
_VALIDATION_ROLE = "agent"


@dataclass(frozen=True)
class AgentManifest:
    agent_id: str
    version: str
    binding: dict[str, Any]
    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    root: Path | None = None  # package dir (None when loaded from a bare yaml)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "format": AGENT_FORMAT,
            "agent_id": self.agent_id,
            "version": self.version,
            "binding": copy.deepcopy(self.binding),
        }
        if self.label:
            out["label"] = self.label
        if self.description:
            out["description"] = self.description
        if self.tags:
            out["tags"] = list(self.tags)
        return out


def _optional_str(raw: Any, *, key: str, location: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"{key} must be a non-empty string when set",
            location=f"{location}:/{key}",
        )
    return raw.strip()


def parse_agent_document(raw: Any, *, location: str = AGENT_FILENAME) -> AgentManifest:
    """Validate a loaded ``agent.yaml`` mapping into an :class:`AgentManifest`."""
    if not isinstance(raw, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent document root must be a mapping",
            location=location,
        )
    fmt = raw.get("format")
    if fmt != AGENT_FORMAT:
        raise ConfigError(
            ERROR_INVALID_FORMAT,
            f"agent format must be {AGENT_FORMAT}; got {fmt!r}",
            location=f"{location}:/format",
        )
    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unknown agent keys: {sorted(unknown)}",
            location=location,
        )

    agent_id_raw = raw.get("agent_id")
    if not isinstance(agent_id_raw, str) or not _AGENT_ID_RE.fullmatch(agent_id_raw.strip()):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_id must match ^[a-z0-9][a-z0-9_-]*$ (optionally org/name)",
            location=f"{location}:/agent_id",
        )
    agent_id = agent_id_raw.strip()

    version_raw = raw.get("version")
    if not isinstance(version_raw, str) or not version_raw.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "version must be a non-empty string",
            location=f"{location}:/version",
        )
    version = version_raw.strip()

    label = _optional_str(raw.get("label"), key="label", location=location)
    description = _optional_str(raw.get("description"), key="description", location=location)

    tags_raw = raw.get("tags")
    tags: tuple[str, ...] = ()
    if tags_raw is not None:
        if not isinstance(tags_raw, list) or not all(
            isinstance(t, str) and t.strip() for t in tags_raw
        ):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "tags must be a list of non-empty strings",
                location=f"{location}:/tags",
            )
        tags = tuple(t.strip() for t in tags_raw)

    binding_raw = raw.get("binding")
    if not isinstance(binding_raw, dict) or not binding_raw:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "binding must be a non-empty mapping (one ageval.profiles/1 binding)",
            location=f"{location}:/binding",
        )
    if "agent_ref" in binding_raw:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "binding.agent_ref is reserved (injected by --agent projection)",
            location=f"{location}:/binding/agent_ref",
        )
    parsed = parse_profiles_mapping(
        {"format": PROFILES_FORMAT, "bindings": {_VALIDATION_ROLE: binding_raw}},
        location=f"{location}:/binding",
    )
    binding = parsed[_VALIDATION_ROLE]
    if label and "label" not in binding:
        binding["label"] = label

    return AgentManifest(
        agent_id=agent_id,
        version=version,
        binding=binding,
        label=label,
        description=description,
        tags=tags,
    )


def _package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git", ".ageval"}]
        for name in filenames:
            files.append(Path(dirpath) / name)
    return sorted(files)


def load_agent_manifest(path: Path) -> AgentManifest:
    """Load ``agent.yaml`` from a package dir or a direct yaml path.

    Fail closed on schema errors, on secret material anywhere in the
    package (locator names are fine; values are not), and when
    ``binding.overlays`` lists a path that is missing from the package.
    """
    path = path.expanduser().resolve(strict=False)
    if path.is_dir():
        root: Path | None = path
        yaml_path = path / AGENT_FILENAME
    else:
        root = None
        yaml_path = path
    if not yaml_path.is_file():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"agent manifest not found: {yaml_path}",
            location=str(yaml_path),
        )
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"invalid YAML: {exc}",
            location=str(yaml_path),
        ) from exc
    manifest = parse_agent_document(data, location=str(yaml_path))

    scan_files = _package_files(root) if root is not None else [yaml_path]
    scan_overlay_files(scan_files, location=str(yaml_path))
    listed = parse_overlay_paths(
        manifest.binding.get("overlays"),
        location=f"{yaml_path}:/binding/overlays",
    )
    if listed:
        # Direct agent.yaml: listed overlays resolve from the sibling package dir.
        assert_overlays_at_lock(
            root if root is not None else yaml_path.parent,
            manifest.binding,
            location=f"{yaml_path}:/binding/overlays",
        )

    return AgentManifest(
        agent_id=manifest.agent_id,
        version=manifest.version,
        binding=manifest.binding,
        label=manifest.label,
        description=manifest.description,
        tags=manifest.tags,
        root=root,
    )
