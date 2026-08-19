"""ageval.plugin/1 archive + digest helpers (separate from Dataset packages)."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import tarfile
from pathlib import Path

from ageval.plugins.manifest import PLUGIN_FORMAT, load_manifest
from ageval.plugins.store import compute_tree_digest
from ageval.registry.media_types import PLUGIN_MEDIA_TYPE as PLUGIN_MEDIA_TYPE

__all__ = [
    "PLUGIN_MEDIA_TYPE",
    "build_plugin_archive",
    "compute_plugin_digest",
    "member_paths_for_plugin",
]


def member_paths_for_plugin(root: Path) -> list[str]:
    """Stable posix-relative file paths under a plugin package root."""
    root = root.expanduser().resolve(strict=False)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git", ".ageval"}]
        for name in filenames:
            if name.endswith(".pyc") or name == ".env":
                continue
            path = Path(dirpath) / name
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            out.append(rel)
    return sorted(out)


def compute_plugin_digest(root: Path) -> str:
    """Package digest for plugins — same tree algorithm as local install cache."""
    return compute_tree_digest(root)


def build_plugin_archive(root: Path) -> tuple[bytes, str, int]:
    """Return ``(archive_bytes, blob_digest, size)`` for a plugin package root."""
    root = root.expanduser().resolve(strict=False)
    # Validate manifest before packaging.
    load_manifest(root)
    paths = member_paths_for_plugin(root)
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        seen_dirs: set[str] = set()
        for rel in paths:
            parts = Path(rel).parts
            for i in range(1, len(parts)):
                d = "/".join(parts[:i])
                if d in seen_dirs:
                    continue
                seen_dirs.add(d)
                info = tarfile.TarInfo(name=d)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                tar.addfile(info)
            abs_path = root / rel
            info = tarfile.TarInfo(name=rel)
            info.size = abs_path.stat().st_size
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with abs_path.open("rb") as fh:
                tar.addfile(info, fh)
    raw_tar = tar_buf.getvalue()
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0) as gz:
        gz.write(raw_tar)
    archive = gz_buf.getvalue()
    blob_digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    return archive, blob_digest, len(archive)


def assert_plugin_package(root: Path) -> None:
    """Fail closed if *root* is not a valid ageval.plugin/1 tree."""
    man = load_manifest(root)
    if man.format != PLUGIN_FORMAT:
        raise ValueError(f"expected {PLUGIN_FORMAT}")
    # Must not look like a Dataset package claimed as plugin without manifest
    # (manifest already required). Dataset-only trees fail at load_manifest.
