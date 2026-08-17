"""Runtime plaza derives harness cards from official public board suites."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from services.registry.access import AccessPolicy
from services.registry.app import build_default_state
from services.registry.errors import RegistryAppError
from services.registry.http_api import RegistryHttpApi
from services.registry.package_service import PackageService
from services.registry.result_service import ResultService
from services.registry.runtime_service import RuntimeService
from services.registry.store import MemoryBlobStore, MetadataStore, TokenInfo

from bora.config.runtime_identity import harness_fingerprint
from bora.registry.archive import MEDIA_TYPE, build_archive
from bora.registry.digest import compute_package_digest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"

NOOA = {
    "executor": "nooa",
    "extensions": [{"plugin": "nooa", "options": {"agent": "nooa"}}],
    "model": "m1",
}
GROK = {
    "executor": "acp",
    "extensions": [{"plugin": "acp", "options": {"entry": "grok-build"}}],
    "model": "g1",
    "api_key": "OPENAI_API_KEY",
}
CODEX = {
    "executor": "acp",
    "extensions": [{"plugin": "acp", "options": {"entry": "codex"}}],
    "model": "g1",
}


def _services(tmp_path: Path) -> tuple[PackageService, ResultService, RuntimeService]:
    meta = MetadataStore(tmp_path / "meta.sqlite3")
    blobs = MemoryBlobStore()
    access = AccessPolicy(meta=meta)
    packages = PackageService(meta, blobs, access, max_upload=64 * 1024 * 1024)
    results = ResultService(meta, blobs, access, max_upload=64 * 1024 * 1024)
    return packages, results, RuntimeService(meta, results)


def _as_path(tmp_path: Path, data: bytes, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _publish(
    packages: PackageService,
    tmp_path: Path,
    *,
    database_id: str,
    org_id: str,
    version: str = "0.1.0",
    slot: str | None = None,
    visibility: str = "public",
) -> None:
    if packages.meta.get_org(org_id) is None:
        packages.meta.create_org(name=org_id, owner_user_id="alice", display_name=org_id)
    archive, blob_digest, size = build_archive(FIXTURE)
    meta: dict[str, object] = {
        "database_id": database_id,
        "version": version,
        "package_digest": compute_package_digest(FIXTURE),
        "blob_digest": blob_digest,
        "media_type": MEDIA_TYPE,
        "visibility": visibility,
        "org_id": org_id,
        "size": size,
    }
    if slot:
        meta["slot"] = slot
    packages.publish(
        meta=meta,
        archive=_as_path(tmp_path, archive, f"{org_id}-{database_id.replace('/', '_')}.tar.gz"),
        auth=TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice"),
    )


def _suite_meta(
    tmp_path: Path,
    *,
    suite_run_id: str,
    database_id: str,
    bindings: dict[str, dict[str, object]] | None,
    visibility: str = "public",
    version: str = "0.1.0",
    task_refs: list[dict[str, object]] | None = None,
    extra_overlay: dict[str, object] | None = None,
    pass_rate: float = 0.4,
    mean_score: float = 0.4,
) -> tuple[dict[str, object], Path]:
    archive = suite_run_id.encode()
    blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    overlay: dict[str, object] | None = None
    if bindings is not None:
        overlay = {"bindings": bindings}
        if extra_overlay:
            overlay.update(extra_overlay)
    meta: dict[str, object] = {
        "suite_run_id": suite_run_id,
        "database_id": database_id,
        "database_version": version,
        "visibility": visibility,
        "blob_digest": blob,
        "size": len(archive),
        "pass_rate": pass_rate,
        "mean_score": mean_score,
        "metrics": {"pass_rate": pass_rate, "n_attempts": 1},
        "task_refs": task_refs
        if task_refs is not None
        else [{"task_id": "hello", "status": "PASS", "score": 1.0}],
    }
    if overlay is not None:
        meta["job_overlay"] = overlay
    return meta, _as_path(tmp_path, archive, f"{suite_run_id}.bin")


def _upload(
    results: ResultService,
    tmp_path: Path,
    **kwargs: object,
) -> dict[str, object]:
    meta, archive = _suite_meta(tmp_path, **kwargs)  # type: ignore[arg-type]
    return results.upload_suite(
        meta=meta,
        archive=archive,
        auth=TokenInfo(scopes=frozenset({"results:upload"}), user_id="alice"),
    )


def test_official_public_suite_appears_community_does_not(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _publish(packages, tmp_path, database_id="acme/looks-official", org_id="acme")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_official",
        database_id="official/gaia",
        bindings={"solver": dict(GROK)},
    )
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_community",
        database_id="acme/looks-official",
        bindings={"solver": dict(GROK)},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    assert [i["runtime_id"] for i in listed["items"]] == [harness_fingerprint(GROK)]
    official_suites = results.list_suites(
        auth=TokenInfo(scopes=frozenset(), user_id=""),
        database_id=None,
    )
    by_id = {i["suite_run_id"]: i for i in official_suites["items"]}
    assert "runtime_refs" in by_id["suite_official"]
    assert "runtime_refs" not in by_id["suite_community"]


def test_private_incomplete_draft_excluded(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _publish(
        packages,
        tmp_path,
        database_id="official/gaia-draft",
        org_id="official",
        slot="draft",
        visibility="private",
    )
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_private",
        database_id="official/gaia",
        bindings={"solver": dict(NOOA)},
        visibility="private",
    )
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_incomplete",
        database_id="official/gaia",
        bindings={"solver": dict(NOOA)},
        task_refs=[],
    )
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_draft",
        database_id="official/gaia-draft",
        version="0.1.0",
        bindings={"solver": dict(NOOA)},
    )
    listed = runtimes.list_runtimes(
        TokenInfo(scopes=frozenset({"results:upload"}), user_id="alice")
    )
    assert listed["items"] == []
    jobs = results.list_suites(
        auth=TokenInfo(scopes=frozenset({"results:upload"}), user_id="alice"),
        database_id=None,
    )
    for item in jobs["items"]:
        assert "runtime_refs" not in item


def test_same_harness_two_roles_one_card(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_duo",
        database_id="official/gaia",
        bindings={"service": dict(NOOA), "user": dict(NOOA)},
        pass_rate=0.5,
        mean_score=0.5,
    )
    auth = TokenInfo(scopes=frozenset(), user_id="")
    listed = runtimes.list_runtimes(auth)
    assert len(listed["items"]) == 1
    rid = listed["items"][0]["runtime_id"]
    assert rid == harness_fingerprint(NOOA)
    assert listed["items"][0]["n_appearances"] == 2
    assert listed["items"][0]["n_datasets"] == 1
    detail = runtimes.get_runtime(runtime_id=rid, auth=auth)
    roles = [a["role"] for a in detail["appearances"]]
    assert roles == ["service", "user"]
    assert {a["pass_rate"] for a in detail["appearances"]} == {0.5}
    assert {a["mean_score"] for a in detail["appearances"]} == {0.5}
    service = next(a for a in detail["appearances"] if a["role"] == "service")
    assert [t["role"] for t in service["teammates"]] == ["user"]
    assert "api_key" not in json.dumps(listed)
    assert "api_key" not in json.dumps(detail["options"])


def test_heterogeneous_bindings_two_cards(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_mix",
        database_id="official/gaia",
        bindings={"solver": dict(GROK), "reviewer": dict(CODEX)},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    ids = {i["runtime_id"] for i in listed["items"]}
    assert ids == {harness_fingerprint(GROK), harness_fingerprint(CODEX)}
    grok = runtimes.get_runtime(
        runtime_id=harness_fingerprint(GROK),
        auth=TokenInfo(scopes=frozenset(), user_id=""),
    )
    assert grok["appearances"][0]["role"] == "solver"
    assert grok["appearances"][0]["teammates"][0]["role"] == "reviewer"
    assert grok["appearances"][0]["teammates"][0]["entry"] == "codex"
    assert "OPENAI_API_KEY" not in json.dumps(grok)
    assert grok["options"] == {"entry": "grok-build"}


def test_same_harness_different_models_one_card(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    grok_g1 = dict(GROK)
    grok_g2 = dict(GROK)
    grok_g2["model"] = "g2"
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_g1",
        database_id="official/gaia",
        bindings={"solver": grok_g1},
    )
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_g2",
        database_id="official/gaia",
        bindings={"solver": grok_g2},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    assert [i["runtime_id"] for i in listed["items"]] == [harness_fingerprint(GROK)]
    assert listed["items"][0]["n_appearances"] == 2
    detail = runtimes.get_runtime(
        runtime_id=harness_fingerprint(GROK),
        auth=TokenInfo(scopes=frozenset(), user_id=""),
    )
    models = {a["model"] for a in detail["appearances"]}
    assert models == {"g1", "g2"}


def test_unknown_runtime_is_404(tmp_path: Path) -> None:
    _packages, _results, runtimes = _services(tmp_path)
    with pytest.raises(RegistryAppError) as ei:
        runtimes.get_runtime(
            runtime_id="rt_unknown",
            auth=TokenInfo(scopes=frozenset(), user_id=""),
        )
    assert ei.value.http_status == 404
    assert ei.value.error == "not_found"
    state, token = build_default_state(tmp_path / "http", bootstrap_token="tok", memory_blob=True)
    api = RegistryHttpApi(state)
    result = api.dispatch(
        method="GET",
        path="/v1/runtimes/rt_unknown",
        headers={"Authorization": f"Bearer {token}"},
        body=BytesIO(),
        content_length=0,
    )
    assert result.status == 404
    payload = json.loads(result.body.decode("utf-8"))
    assert payload["error"] == "not_found"
    assert "message" in payload


def test_display_name_prefers_binding_label(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    labeled = dict(GROK)
    labeled["label"] = "pi-agent"
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_label",
        database_id="official/gaia",
        bindings={"solver": labeled},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    assert listed["items"][0]["display_name"] == "pi-agent"
    assert listed["items"][0]["entry"] == "grok-build"
    assert listed["items"][0]["executor"] == "acp"


def test_team_overlay_still_extracts_members(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_team",
        database_id="official/gaia",
        bindings={"service": dict(NOOA), "user": dict(NOOA)},
        extra_overlay={"team": {"enabled": True}},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    assert len(listed["items"]) == 1
    assert listed["items"][0]["display_name"] == "Nooa"


def test_bare_acp_is_not_projected(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_acp_only",
        database_id="official/gaia",
        bindings={"solver": {"executor": "acp", "model": "g1"}},
    )
    listed = runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))
    assert listed["items"] == []
    suites = results.list_suites(
        auth=TokenInfo(scopes=frozenset(), user_id=""),
        database_id=None,
    )
    assert suites["items"][0].get("runtime_refs") in (None, [])


def test_no_overlay_skipped(tmp_path: Path) -> None:
    packages, results, runtimes = _services(tmp_path)
    _publish(packages, tmp_path, database_id="official/gaia", org_id="official")
    _upload(
        results,
        tmp_path,
        suite_run_id="suite_bare",
        database_id="official/gaia",
        bindings=None,
    )
    assert runtimes.list_runtimes(TokenInfo(scopes=frozenset(), user_id=""))["items"] == []
