"""Deterministic Database archive (tar + gzip) and extract.

Media type (v1 freeze): ``application/vnd.ageval.database.v1.tar+gzip``

Determinism rules:
- member order = sorted package-relative paths (same as packageDigest input)
- tar mtime = 0, uid = gid = 0, uname = gname = ""
- mode = 0o644 for files, 0o755 for dirs
- gzip mtime = 0
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path
from typing import Any

from ageval.config.database import member_paths_for_digest
from ageval.registry.media_types import DATABASE_MEDIA_TYPE

MEDIA_TYPE = DATABASE_MEDIA_TYPE


def write_archive(database_root: Path, dest: Path) -> tuple[str, int]:
    """Write a deterministic tar.gz to *dest*. Return ``(blob_digest, size)``."""
    root = database_root.expanduser().resolve(strict=False)
    paths = member_paths_for_digest(root)
    dest = dest.expanduser().resolve(strict=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tar_tmp = dest.with_name(dest.name + ".tar.tmp")
    try:
        with tarfile.open(name=tar_tmp, mode="w", format=tarfile.PAX_FORMAT) as tar:
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
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mode = 0o755
                    tar.addfile(info)
                abs_path = root / rel
                data = abs_path.read_bytes()
                info = tarfile.TarInfo(name=rel)
                info.size = len(data)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
        with (
            dest.open("wb") as out,
            gzip.GzipFile(fileobj=out, mode="wb", mtime=0, compresslevel=9) as gz,
            tar_tmp.open("rb") as inf,
        ):
            while True:
                block = inf.read(1024 * 1024)
                if not block:
                    break
                gz.write(block)
    finally:
        tar_tmp.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with dest.open("rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return f"sha256:{digest.hexdigest()}", dest.stat().st_size


def build_archive(database_root: Path) -> tuple[bytes, str, int]:
    """Return ``(archive_bytes, blob_digest, size)`` for small fixtures/tests."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ageval-arch-") as tmp:
        dest = Path(tmp) / "pkg.tar.gz"
        digest, size = write_archive(database_root, dest)
        return dest.read_bytes(), digest, size


def extract_archive(archive: bytes | Path, dest_root: Path) -> None:
    """Extract archive into *dest_root* (must not already exist as non-empty)."""
    dest_root = dest_root.expanduser().resolve(strict=False)
    dest_root.mkdir(parents=True, exist_ok=True)
    closer: Any = None
    if isinstance(archive, Path):
        fileobj: Any = archive.open("rb")
        closer = fileobj
    else:
        fileobj = io.BytesIO(archive)
    try:
        with (
            gzip.GzipFile(fileobj=fileobj, mode="rb") as gz,
            tarfile.open(fileobj=gz, mode="r:") as tar,
        ):
            try:
                tar.extractall(path=dest_root, filter="data")  # type: ignore[call-arg]
            except TypeError:
                tar.extractall(path=dest_root)  # noqa: S202 — trusted registry bytes after digest
    finally:
        if closer is not None:
            closer.close()
