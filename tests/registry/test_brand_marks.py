"""Closed catalog icon_key: allowlist + package PATCH."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from services.registry.access import AccessPolicy
from services.registry.brand_marks import ALLOWED_KEYS
from services.registry.errors import RegistryAppError
from services.registry.package_service import PackageService
from services.registry.store import MemoryBlobStore, MetadataStore, TokenInfo

from ageval.registry.archive import MEDIA_TYPE, build_archive
from ageval.registry.digest import compute_package_digest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "datasets" / "publish-min"


def _service(tmp_path: Path) -> PackageService:
    meta = MetadataStore(tmp_path / "meta.sqlite3")
    blobs = MemoryBlobStore()
    return PackageService(meta, blobs, AccessPolicy(meta=meta), max_upload=64 * 1024 * 1024)


def _meta_archive(tmp_path: Path) -> tuple[dict[str, object], Path]:
    archive, blob_digest, size = build_archive(FIXTURE)
    path = tmp_path / "pkg.tar.gz"
    path.write_bytes(archive)
    return (
        {
            "dataset_id": "test/publish-min",
            "version": "0.1.0",
            "package_digest": compute_package_digest(FIXTURE),
            "blob_digest": blob_digest,
            "media_type": MEDIA_TYPE,
            "visibility": "private",
            "org_id": "acme",
            "size": size,
        },
        path,
    )


def test_hub_catalog_keys_match_registry_allowlist() -> None:
    allow = json.loads(
        (REPO / "services/registry/brand_marks.json").read_text(encoding="utf-8"),
    )
    ts = (REPO / "apps/hub/src/lib/brand-marks/catalog.ts").read_text(encoding="utf-8")
    ids = re.findall(r'id: "([a-z0-9-]+)"', ts)
    assert sorted(allow) == sorted(ids)
    assert frozenset(allow) == ALLOWED_KEYS


def test_patch_icon_key_roundtrip(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    meta, archive = _meta_archive(tmp_path)
    auth = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    svc.publish(meta=meta, archive=archive, auth=auth)

    stored = svc.patch_marketplace(
        dataset_id="test/publish-min",
        auth=auth,
        icon_key="docker",
        has_icon_key=True,
    )
    assert stored["icon_key"] == "docker"

    listed = svc.list_packages(
        auth=auth,
        prefix=None,
        visibility=None,
        version=None,
        package_kind=None,
    )
    row = next(i for i in listed["items"] if i["dataset_id"] == "test/publish-min")
    assert row["icon_key"] == "docker"

    got = svc.serve_meta(
        dataset_id="test/publish-min",
        version="0.1.0",
        package_digest=None,
        auth=auth,
    )
    assert got["icon_key"] == "docker"

    cleared = svc.patch_marketplace(
        dataset_id="test/publish-min",
        auth=auth,
        icon_key="",
        has_icon_key=True,
    )
    assert "icon_key" not in cleared

    with pytest.raises(RegistryAppError) as ei:
        svc.patch_marketplace(
            dataset_id="test/publish-min",
            auth=auth,
            icon_key="not-a-brand",
            has_icon_key=True,
        )
    assert ei.value.error == "invalid_request"
    assert ei.value.http_status == 400
