"""Leaderboard completeness is computed at suite upload (not SPA-only)."""

from __future__ import annotations

from pathlib import Path

from services.registry.access import AccessPolicy
from services.registry.package_service import PackageService
from services.registry.result_service import ResultService
from services.registry.store import MemoryBlobStore, MetadataStore, TokenInfo

from bora.registry.archive import MEDIA_TYPE, build_archive
from bora.registry.digest import compute_package_digest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"


def _services(tmp_path: Path) -> tuple[PackageService, ResultService]:
    meta = MetadataStore(tmp_path / "meta.sqlite3")
    blobs = MemoryBlobStore()
    access = AccessPolicy(meta=meta)
    packages = PackageService(meta, blobs, access, max_upload=64 * 1024 * 1024)
    results = ResultService(meta, blobs, access, max_upload=64 * 1024 * 1024)
    return packages, results


def _publish_release(packages: PackageService) -> None:
    archive, blob_digest, size = build_archive(FIXTURE)
    packages.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    auth = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    packages.publish(
        meta={
            "database_id": "test/publish-min",
            "version": "0.1.0",
            "package_digest": compute_package_digest(FIXTURE),
            "blob_digest": blob_digest,
            "media_type": MEDIA_TYPE,
            "visibility": "public",
            "org_id": "acme",
            "size": size,
        },
        archive=archive,
        auth=auth,
    )


def _suite_meta(
    *,
    suite_run_id: str,
    task_refs: list[dict[str, object]],
    version: str = "0.1.0",
) -> tuple[dict[str, object], bytes]:
    archive = b"suite-archive"
    import hashlib

    blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    return (
        {
            "suite_run_id": suite_run_id,
            "database_id": "test/publish-min",
            "database_version": version,
            "visibility": "public",
            "blob_digest": blob,
            "size": len(archive),
            "pass_rate": 0.0,
            "mean_score": 0.0,
            "metrics": {"n_tasks": len(task_refs)},
            "task_refs": task_refs,
        },
        archive,
    )


def test_fail_on_all_tasks_is_complete_and_on_board(tmp_path: Path) -> None:
    packages, results = _services(tmp_path)
    _publish_release(packages)
    auth = TokenInfo(scopes=frozenset({"results:upload"}), user_id="alice")
    meta, archive = _suite_meta(
        suite_run_id="suite_fail_all",
        task_refs=[{"task_id": "hello", "status": "FAIL", "score": 0.0}],
    )
    payload = results.upload_suite(meta=meta, archive=archive, auth=auth)
    assert payload["complete"] is True
    assert payload["bound_kind"] == "release"
    board = results.list_suites(auth=auth, database_id="test/publish-min", board=True)
    assert [i["suite_run_id"] for i in board["items"]] == ["suite_fail_all"]


def test_missing_task_is_incomplete_hidden_from_board(tmp_path: Path) -> None:
    packages, results = _services(tmp_path)
    _publish_release(packages)
    auth = TokenInfo(scopes=frozenset({"results:upload"}), user_id="alice")
    meta, archive = _suite_meta(
        suite_run_id="suite_missing",
        task_refs=[],
    )
    payload = results.upload_suite(meta=meta, archive=archive, auth=auth)
    assert payload["complete"] is False
    board = results.list_suites(auth=auth, database_id="test/publish-min", board=True)
    jobs = results.list_suites(auth=auth, database_id="test/publish-min", board=False)
    assert board["items"] == []
    assert [i["suite_run_id"] for i in jobs["items"]] == ["suite_missing"]


def test_draft_bound_suite_stays_off_public_board(tmp_path: Path) -> None:
    packages, results = _services(tmp_path)
    packages.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    archive, blob_digest, size = build_archive(FIXTURE)
    alice = TokenInfo(scopes=frozenset({"registry:publish", "results:upload"}), user_id="alice")
    packages.publish(
        meta={
            "database_id": "test/publish-min",
            "version": "0.1.0",
            "package_digest": compute_package_digest(FIXTURE),
            "blob_digest": blob_digest,
            "media_type": MEDIA_TYPE,
            "visibility": "private",
            "org_id": "acme",
            "size": size,
            "slot": "draft",
        },
        archive=archive,
        auth=alice,
    )
    meta, sarch = _suite_meta(
        suite_run_id="suite_draft",
        version="0.1.0",
        task_refs=[{"task_id": "hello", "status": "PASS", "score": 1.0}],
    )
    payload = results.upload_suite(meta=meta, archive=sarch, auth=alice)
    assert payload["bound_kind"] == "draft"
    assert payload["complete"] is True
    board = results.list_suites(auth=alice, database_id="test/publish-min", board=True)
    jobs = results.list_suites(auth=alice, database_id="test/publish-min", board=False)
    assert board["items"] == []
    assert jobs["items"][0]["suite_run_id"] == "suite_draft"


def test_later_draft_task_does_not_drop_old_release_run(tmp_path: Path) -> None:
    packages, results = _services(tmp_path)
    _publish_release(packages)
    auth = TokenInfo(scopes=frozenset({"registry:publish", "results:upload"}), user_id="alice")
    meta, archive = _suite_meta(
        suite_run_id="suite_release",
        task_refs=[{"task_id": "hello", "status": "PASS", "score": 1.0}],
    )
    results.upload_suite(meta=meta, archive=archive, auth=auth)
    # Overwrite draft with the same package (simulates later draft edit).
    pkg, blob_digest, size = build_archive(FIXTURE)
    packages.publish(
        meta={
            "database_id": "test/publish-min",
            "version": "0.1.0",
            "package_digest": compute_package_digest(FIXTURE),
            "blob_digest": blob_digest,
            "media_type": MEDIA_TYPE,
            "visibility": "private",
            "org_id": "acme",
            "size": size,
            "slot": "draft",
        },
        archive=pkg,
        auth=auth,
    )
    board = results.list_suites(auth=auth, database_id="test/publish-min", board=True)
    assert [i["suite_run_id"] for i in board["items"]] == ["suite_release"]
    assert board["items"][0]["complete"] is True
