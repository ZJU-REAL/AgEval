"""Plugin cache index + digest + install/uninstall (constitution §7.1B / §7.5)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ageval.plugins.manifest import PluginManifestError, load_manifest
from ageval.plugins.paths import index_path, package_dir, plugins_root

# Process-local index. Keyed by path + mtime + size so a write on disk
# (install, uninstall, or a test replacing the file) is seen on the next read.
_UNSET = object()
_index_cache: PluginIndex | None = None
_index_cache_key: object = _UNSET


def _index_file_key(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), int(st.st_mtime_ns), int(st.st_size))


@dataclass
class IndexEntry:
    plugin_id: str
    version: str
    digest: str
    path: str  # relative to plugins_root
    format: str
    slots_summary: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "digest": self.digest,
            "path": self.path,
            "format": self.format,
            "slots_summary": self.slots_summary,
        }


@dataclass
class PluginIndex:
    plugins: list[IndexEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"plugins": [p.as_dict() for p in self.plugins]}

    def find(self, plugin_id: str) -> IndexEntry | None:
        for p in self.plugins:
            if p.plugin_id == plugin_id:
                return p
        return None


def compute_tree_digest(root: Path) -> str:
    """SHA-256 over sorted relative paths + file contents (stable package digest).

    Algorithm: for each regular file under *root* (skip __pycache__, .git),
    feed ``relpath\\0`` + file bytes into a streaming sha256; return ``sha256:<hex>``.
    """
    h = hashlib.sha256()
    root = root.resolve(strict=False)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git", ".ageval"}]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            files.append(Path(dirpath) / name)
    for path in sorted(files, key=lambda p: str(p.relative_to(root)).replace(os.sep, "/")):
        rel = str(path.relative_to(root)).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def load_index() -> PluginIndex:
    global _index_cache, _index_cache_key
    path = index_path()
    key = _index_file_key(path)
    if _index_cache is not None and _index_cache_key == key:
        return PluginIndex(plugins=list(_index_cache.plugins))
    if key is None:
        _index_cache = PluginIndex()
        _index_cache_key = None
        return PluginIndex()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _index_cache = PluginIndex()
        _index_cache_key = key
        return PluginIndex()
    plugins_raw = raw.get("plugins") if isinstance(raw, dict) else None
    if not isinstance(plugins_raw, list):
        _index_cache = PluginIndex()
        _index_cache_key = key
        return PluginIndex()
    entries: list[IndexEntry] = []
    for row in plugins_raw:
        if not isinstance(row, dict):
            continue
        try:
            entries.append(
                IndexEntry(
                    plugin_id=str(row["plugin_id"]),
                    version=str(row["version"]),
                    digest=str(row["digest"]),
                    path=str(row["path"]),
                    format=str(row.get("format") or "ageval.plugin/1"),
                    slots_summary=dict(row.get("slots_summary") or {}),
                )
            )
        except KeyError:
            continue
    _index_cache = PluginIndex(plugins=entries)
    _index_cache_key = key
    return PluginIndex(plugins=list(entries))


def save_index(index: PluginIndex) -> None:
    global _index_cache, _index_cache_key
    root = plugins_root()
    root.mkdir(parents=True, exist_ok=True)
    path = index_path()
    payload = json.dumps(index.as_dict(), indent=2, sort_keys=True) + "\n"
    # Atomic write: temp in same dir then replace.
    fd, tmp_name = tempfile.mkstemp(prefix=".index.", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib_suppress():
            os.unlink(tmp_name)
        raise
    _index_cache = PluginIndex(plugins=list(index.plugins))
    _index_cache_key = _index_file_key(path)


class contextlib_suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> bool:
        return True


def install_from_path(source: Path, *, plugin_id: str | None = None) -> IndexEntry:
    """Copy a plugin package into the local cache and update index.

    Does **not** modify project profiles / ageval.yaml / task.yaml (§7.5).
    *plugin_id* overrides the manifest id (Hub install records ``org/name``).
    """
    source = source.expanduser().resolve(strict=False)
    if not source.is_dir():
        raise PluginManifestError(f"plugin path is not a directory: {source}")

    manifest = load_manifest(source)
    resolved_id = plugin_id.strip() if isinstance(plugin_id, str) and plugin_id.strip() else None
    index_id = resolved_id or manifest.plugin_id
    digest = compute_tree_digest(source)
    rel = f"{index_id}/{manifest.version}"
    dest = package_dir(index_id, manifest.version)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_prefix = index_id.replace("/", ".")

    # Idempotent: same digest already installed.
    if dest.is_dir():
        existing = compute_tree_digest(dest)
        if existing == digest:
            entry = IndexEntry(
                plugin_id=index_id,
                version=manifest.version,
                digest=digest,
                path=rel,
                format=manifest.format,
                slots_summary=manifest.slots_summary(),
            )
            _upsert_index(entry)
            return entry
        # Different content at same version → replace atomically via temp.
        shutil.rmtree(dest)

    tmp_parent = dest.parent
    tmp = Path(tempfile.mkdtemp(prefix=f".{tmp_prefix}.", dir=str(tmp_parent)))
    try:
        shutil.copytree(source, tmp / "pkg")
        os.replace(tmp / "pkg", dest)
    finally:
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)

    # Verify digest after copy.
    got = compute_tree_digest(dest)
    if got != digest:
        shutil.rmtree(dest, ignore_errors=True)
        raise PluginManifestError(
            "digest mismatch after install",
            kind="plugin_digest_mismatch",
        )

    entry = IndexEntry(
        plugin_id=index_id,
        version=manifest.version,
        digest=digest,
        path=rel,
        format=manifest.format,
        slots_summary=manifest.slots_summary(),
    )
    _upsert_index(entry)
    return entry


def _upsert_index(entry: IndexEntry) -> None:
    index = load_index()
    index.plugins = [p for p in index.plugins if p.plugin_id != entry.plugin_id]
    index.plugins.append(entry)
    index.plugins.sort(key=lambda p: p.plugin_id)
    save_index(index)


def uninstall(plugin_id: str) -> bool:
    """Remove package dir + index row. Does not touch profiles."""
    index = load_index()
    entry = index.find(plugin_id)
    if entry is None:
        return False
    dest = plugins_root() / entry.path
    if dest.is_dir():
        shutil.rmtree(dest)
    # Clean empty parent dirs (org/name nests two levels).
    parent = dest.parent
    root = plugins_root()
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    index.plugins = [p for p in index.plugins if p.plugin_id != plugin_id]
    save_index(index)
    return True


def list_installed() -> list[IndexEntry]:
    return list(load_index().plugins)


def resolve_package_root(entry: IndexEntry) -> Path:
    return plugins_root() / entry.path
