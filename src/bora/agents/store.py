"""Agent cache index + install/uninstall (design/14).

Mirrors the plugins cache: install only writes ``$BORA_HOME/agents``; it
never rewrites profiles / task.yaml. Index keys are the local id (short
``agent_id`` recorded as ``local/<agent_id>``) or the Hub id ``org/name``.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bora.agents.manifest import AgentManifest, load_agent_manifest
from bora.agents.paths import agents_root, index_path, package_dir
from bora.config.errors import ERROR_INVALID_PACKAGE, ConfigError
from bora.plugins.store import compute_tree_digest

LOCAL_NAMESPACE = "local"


@dataclass
class AgentIndexEntry:
    agent_id: str  # index id: local/<id> or org/name
    version: str
    digest: str
    path: str  # relative to agents_root
    format: str
    label: str | None = None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "agent_id": self.agent_id,
            "version": self.version,
            "digest": self.digest,
            "path": self.path,
            "format": self.format,
        }
        if self.label:
            out["label"] = self.label
        if self.tags:
            out["tags"] = list(self.tags)
        return out


@dataclass
class AgentIndex:
    agents: list[AgentIndexEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"agents": [a.as_dict() for a in self.agents]}

    def find(self, agent_id: str) -> AgentIndexEntry | None:
        for a in self.agents:
            if a.agent_id == agent_id:
                return a
        return None


def load_index() -> AgentIndex:
    path = index_path()
    if not path.is_file():
        return AgentIndex()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AgentIndex()
    rows = raw.get("agents") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return AgentIndex()
    entries: list[AgentIndexEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            entries.append(
                AgentIndexEntry(
                    agent_id=str(row["agent_id"]),
                    version=str(row["version"]),
                    digest=str(row["digest"]),
                    path=str(row["path"]),
                    format=str(row.get("format") or "bora.agent/1"),
                    label=str(row["label"]) if row.get("label") else None,
                    tags=[str(t) for t in row.get("tags") or []],
                )
            )
        except KeyError:
            continue
    return AgentIndex(agents=entries)


def save_index(index: AgentIndex) -> None:
    root = agents_root()
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index.as_dict(), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".index.", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, index_path())
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def default_index_id(manifest: AgentManifest) -> str:
    """Local-path installs of a short id are namespaced ``local/<agent_id>``."""
    if "/" in manifest.agent_id:
        return manifest.agent_id
    return f"{LOCAL_NAMESPACE}/{manifest.agent_id}"


def install_from_path(source: Path, *, agent_id: str | None = None) -> AgentIndexEntry:
    """Copy an agent package into the local cache and update the index.

    Never modifies project profiles / bora.yaml / task.yaml. *agent_id*
    overrides the index id (Hub install records ``org/name``). Fails closed
    on manifest/secret errors before anything is written.
    """
    source = source.expanduser().resolve(strict=False)
    if not source.is_dir():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"agent path is not a directory: {source}",
            location=str(source),
        )
    manifest = load_agent_manifest(source)
    index_id = (
        agent_id.strip()
        if isinstance(agent_id, str) and agent_id.strip()
        else default_index_id(manifest)
    )
    digest = compute_tree_digest(source)
    rel = f"{index_id}/{manifest.version}"
    dest = package_dir(index_id, manifest.version)
    dest.parent.mkdir(parents=True, exist_ok=True)

    entry = AgentIndexEntry(
        agent_id=index_id,
        version=manifest.version,
        digest=digest,
        path=rel,
        format="bora.agent/1",
        label=manifest.label,
        tags=list(manifest.tags),
    )

    if dest.is_dir():
        if compute_tree_digest(dest) == digest:
            _upsert_index(entry)
            return entry
        shutil.rmtree(dest)

    tmp = Path(tempfile.mkdtemp(prefix=f".{index_id.replace('/', '.')}.", dir=str(dest.parent)))
    try:
        shutil.copytree(source, tmp / "pkg")
        os.replace(tmp / "pkg", dest)
    finally:
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)

    if compute_tree_digest(dest) != digest:
        shutil.rmtree(dest, ignore_errors=True)
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "digest mismatch after agent install",
            location=str(dest),
        )
    _upsert_index(entry)
    return entry


def _upsert_index(entry: AgentIndexEntry) -> None:
    index = load_index()
    index.agents = [a for a in index.agents if a.agent_id != entry.agent_id]
    index.agents.append(entry)
    index.agents.sort(key=lambda a: a.agent_id)
    save_index(index)


def uninstall(agent_id: str) -> bool:
    index = load_index()
    entry = index.find(agent_id)
    if entry is None:
        return False
    dest = agents_root() / entry.path
    if dest.is_dir():
        shutil.rmtree(dest)
    parent = dest.parent
    root = agents_root()
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    index.agents = [a for a in index.agents if a.agent_id != agent_id]
    save_index(index)
    return True


def list_installed() -> list[AgentIndexEntry]:
    return list(load_index().agents)


def resolve_package_root(entry: AgentIndexEntry) -> Path:
    return agents_root() / entry.path


def resolve_installed_ref(agent_id: str, version: str) -> tuple[AgentIndexEntry, Path]:
    """Resolve a pinned ``<id>@<version>`` against the local cache, fail closed."""
    entry = load_index().find(agent_id)
    if entry is None:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"agent not installed: {agent_id!r} (run: bora agent install …)",
            location=agent_id,
        )
    if entry.version != version:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"agent {agent_id!r} installed at version {entry.version!r}, "
            f"requested {version!r} (run: bora agent install)",
            location=f"{agent_id}@{version}",
        )
    root = resolve_package_root(entry)
    if not root.is_dir():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"agent cache missing on disk: {root}",
            location=f"{agent_id}@{version}",
        )
    return entry, root
