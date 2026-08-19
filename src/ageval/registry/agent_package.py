"""ageval.agent/1 archive + digest helpers (design/14; mirrors plugin_package)."""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path

from ageval.agents.manifest import AGENT_FORMAT, load_agent_manifest
from ageval.plugins.store import compute_tree_digest
from ageval.registry.media_types import AGENT_MEDIA_TYPE as AGENT_MEDIA_TYPE
from ageval.registry.plugin_package import member_paths_for_plugin as member_paths_for_agent

__all__ = [
    "AGENT_MEDIA_TYPE",
    "assert_agent_package",
    "build_agent_archive",
    "compute_agent_digest",
    "member_paths_for_agent",
]


def compute_agent_digest(root: Path) -> str:
    """Package digest for agents — same tree algorithm as the local cache."""
    return compute_tree_digest(root)


def assert_agent_package(root: Path) -> None:
    """Fail closed unless *root* is a valid, secret-free ageval.agent/1 tree."""
    load_agent_manifest(root)  # schema + package-wide secret scan
    if (root / "ageval.yaml").is_file() or (root / "plugin.yaml").is_file():
        raise ValueError(f"agent package must not also carry a Dataset/plugin manifest ({root})")
    _ = AGENT_FORMAT  # format pinned by load_agent_manifest


def build_agent_archive(root: Path) -> tuple[bytes, str, int]:
    """Return ``(archive_bytes, blob_digest, size)`` for an agent package root."""
    root = root.expanduser().resolve(strict=False)
    assert_agent_package(root)
    paths = member_paths_for_agent(root)
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
