"""PackageService.publish is a real domain module (no HTTP objects)."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.registry.access import AccessPolicy
from services.registry.errors import RegistryAppError
from services.registry.package_service import PackageService
from services.registry.store import (
    MemoryBlobStore,
    MetadataStore,
    TokenInfo,
)

from bora.registry.archive import MEDIA_TYPE, build_archive
from bora.registry.digest import compute_package_digest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"


def _service(tmp_path: Path) -> PackageService:
    meta = MetadataStore(tmp_path / "meta.sqlite3")
    blobs = MemoryBlobStore()
    return PackageService(meta, blobs, AccessPolicy(meta=meta), max_upload=64 * 1024 * 1024)


def _meta_archive() -> tuple[dict[str, object], bytes]:
    archive, blob_digest, size = build_archive(FIXTURE)
    return (
        {
            "database_id": "test/publish-min",
            "version": "0.1.0",
            "package_digest": compute_package_digest(FIXTURE),
            "blob_digest": blob_digest,
            "media_type": MEDIA_TYPE,
            "visibility": "private",
            "org_id": "acme",
            "size": size,
        },
        archive,
    )


def test_publish_missing_org(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    meta, archive = _meta_archive()
    auth = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    with pytest.raises(RegistryAppError) as ei:
        svc.publish(meta=meta, archive=archive, auth=auth)
    assert ei.value.error == "org_not_found"
    assert ei.value.http_status == 400


def test_publish_requires_membership(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="owner", display_name="Acme")
    meta, archive = _meta_archive()
    auth = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    with pytest.raises(RegistryAppError) as ei:
        svc.publish(meta=meta, archive=archive, auth=auth)
    assert ei.value.error == "forbidden"
    assert ei.value.http_status == 403


def test_publish_happy_path(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    meta, archive = _meta_archive()
    auth = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    payload = svc.publish(meta=meta, archive=archive, auth=auth)
    assert payload["database_id"] == "test/publish-min"
    assert payload["org_id"] == "acme"
    row = svc.get("test/publish-min", "0.1.0")
    assert row is not None
    assert svc.blobs.get(row.blob_digest, prefix="packages") == archive
