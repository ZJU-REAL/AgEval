"""packageDigest + deterministic archive unit tests (Spec 21)."""

from __future__ import annotations

from pathlib import Path

from bora.registry.archive import MEDIA_TYPE, build_archive, extract_archive
from bora.registry.digest import compute_package_digest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"


def test_package_digest_stable() -> None:
    a = compute_package_digest(FIXTURE)
    b = compute_package_digest(FIXTURE)
    assert a == b
    assert a.startswith("sha256:")
    assert len(a) == len("sha256:") + 64


def test_archive_roundtrip_and_blob_digest(tmp_path: Path) -> None:
    archive, blob_digest, size = build_archive(FIXTURE)
    assert size == len(archive)
    assert blob_digest.startswith("sha256:")
    assert MEDIA_TYPE.endswith("gzip")
    dest = tmp_path / "out"
    extract_archive(archive, dest)
    assert (dest / "bora.yaml").is_file()
    assert (dest / "tasks" / "hello" / "task.yaml").is_file()
    assert compute_package_digest(dest) == compute_package_digest(FIXTURE)


def test_archive_bytes_deterministic() -> None:
    a1, d1, s1 = build_archive(FIXTURE)
    a2, d2, s2 = build_archive(FIXTURE)
    assert a1 == a2
    assert d1 == d2
    assert s1 == s2
