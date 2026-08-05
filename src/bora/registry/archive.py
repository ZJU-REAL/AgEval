"""Deterministic Database archive (tar + gzip) and extract.

Media type (v1 freeze): ``application/vnd.bora.database.v1.tar+gzip``

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

from bora.config.database import member_paths_for_digest

MEDIA_TYPE = "application/vnd.bora.database.v1.tar+gzip"


def build_archive(database_root: Path) -> tuple[bytes, str, int]:
    """Return ``(archive_bytes, blob_digest, size)`` for *database_root*."""
    root = database_root.expanduser().resolve(strict=False)
    paths = member_paths_for_digest(root)
    buf = io.BytesIO()
    # Build uncompressed tar first for stable gzip of fixed payload.
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        # Ensure parent dirs are present deterministically.
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
    raw_tar = tar_buf.getvalue()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw_tar)
    archive = buf.getvalue()
    digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    return archive, digest, len(archive)


def extract_archive(archive: bytes, dest_root: Path) -> None:
    """Extract archive into *dest_root* (must not already exist as non-empty)."""
    dest_root = dest_root.expanduser().resolve(strict=False)
    dest_root.mkdir(parents=True, exist_ok=True)
    with (
        gzip.GzipFile(fileobj=io.BytesIO(archive), mode="rb") as gz,
        tarfile.open(fileobj=gz, mode="r:") as tar,
    ):
        # Python 3.12+ filter= for path safety when available.
        try:
            tar.extractall(path=dest_root, filter="data")  # type: ignore[call-arg]
        except TypeError:
            tar.extractall(path=dest_root)  # noqa: S202 — trusted registry bytes after digest
