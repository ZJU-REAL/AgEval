"""Deterministic Attempt result archive (tar + gzip).

Layout inside the archive (paths relative to archive root)::

    .bora/runs/<run_id>/…

Media type: ``application/vnd.bora.attempt-result.v1.tar+gzip``
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path

MEDIA_TYPE = "application/vnd.bora.attempt-result.v1.tar+gzip"


def build_attempt_archive(run_dir: Path, *, run_id: str) -> tuple[bytes, str, int]:
    """Pack ``run_dir`` as ``.bora/runs/<run_id>/…``; return bytes, blob_digest, size."""
    root = run_dir.expanduser().resolve(strict=True)
    if not root.is_dir():
        msg = f"run directory not found: {root}"
        raise FileNotFoundError(msg)

    prefix = f".bora/runs/{run_id}"
    members: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        members.append((f"{prefix}/{rel}", path))

    return _pack_tree(members)


def extract_attempt_archive(archive: bytes, dest_root: Path) -> Path:
    """Extract into *dest_root*; return path to ``.bora/runs/<run_id>`` if found."""
    dest = dest_root.expanduser().resolve(strict=False)
    dest.mkdir(parents=True, exist_ok=True)
    with (
        gzip.GzipFile(fileobj=io.BytesIO(archive), mode="rb") as gz,
        tarfile.open(fileobj=gz, mode="r:") as tar,
    ):
        try:
            tar.extractall(path=dest, filter="data")  # type: ignore[call-arg]
        except TypeError:
            tar.extractall(path=dest)
    runs = dest / ".bora" / "runs"
    if runs.is_dir():
        children = [p for p in runs.iterdir() if p.is_dir()]
        if len(children) == 1:
            return children[0]
    return dest


SUITE_MEDIA_TYPE = "application/vnd.bora.suite-result.v1.tar+gzip"


def _pack_tree(members: list[tuple[str, Path]]) -> tuple[bytes, str, int]:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        seen_dirs: set[str] = set()
        for arcname, abs_path in members:
            parts = Path(arcname).parts
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
            data = abs_path.read_bytes()
            info = tarfile.TarInfo(name=arcname)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(tar_buf.getvalue())
    archive = buf.getvalue()
    digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    return archive, digest, len(archive)


def build_suite_archive(suite_dir: Path, *, suite_run_id: str) -> tuple[bytes, str, int]:
    """Pack ``suite_dir`` as ``.bora/suite-runs/<suite_run_id>/…``."""
    root = suite_dir.expanduser().resolve(strict=True)
    if not root.is_dir():
        msg = f"suite directory not found: {root}"
        raise FileNotFoundError(msg)

    prefix = f".bora/suite-runs/{suite_run_id}"
    members: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        members.append((f"{prefix}/{rel}", path))

    return _pack_tree(members)


def extract_suite_archive(archive: bytes, dest_root: Path) -> Path:
    """Extract suite bundle; return path to ``.bora/suite-runs/<id>`` if found."""
    dest = dest_root.expanduser().resolve(strict=False)
    dest.mkdir(parents=True, exist_ok=True)
    with (
        gzip.GzipFile(fileobj=io.BytesIO(archive), mode="rb") as gz,
        tarfile.open(fileobj=gz, mode="r:") as tar,
    ):
        try:
            tar.extractall(path=dest, filter="data")  # type: ignore[call-arg]
        except TypeError:
            tar.extractall(path=dest)
    suites = dest / ".bora" / "suite-runs"
    if suites.is_dir():
        children = [p for p in suites.iterdir() if p.is_dir()]
        if len(children) == 1:
            return children[0]
    return dest
