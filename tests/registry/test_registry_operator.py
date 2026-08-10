"""Operator surface: list packages, results upload, mocked OAuth login."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from services.registry.app import build_default_state, make_handler
from services.registry.oauth_github import DeviceCodeResponse, GitHubIdentity
from services.registry.store import DEFAULT_LOGIN_SCOPES

from bora.application.publish_command import publish_database
from bora.application.registry_list_command import cache_list, list_packages, show_package
from bora.application.results_command import (
    get_attempt_result,
    get_suite_result,
    list_attempt_results,
    list_suite_results,
    upload_attempt_result,
    upload_suite_result,
)
from bora.registry.client import RegistryClient
from bora.registry.credentials import write_credentials

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"

TEST_ORG = "test"


def _ensure_org() -> None:
    """Create default test org owned by current token (idempotent)."""
    import os

    from bora.registry.client import RegistryClient, RegistryError

    url = os.environ.get("BORA_REGISTRY_URL") or ""
    token = os.environ.get("BORA_REGISTRY_TOKEN") or ""
    if not url or not token:
        return
    client = RegistryClient(url, token=token)
    try:
        client.create_org(name=TEST_ORG, display_name="Test Org")
    except RegistryError:
        return


@pytest.fixture()
def registry_server(tmp_path: Path):
    data = tmp_path / "reg-data"
    state, token = build_default_state(data, bootstrap_token="test-token-publish", memory_blob=True)
    # Enable OAuth config for login tests (mocked GitHub).
    state.github_client_id = "test-client-id"
    state.github_client_secret = "test-client-secret"
    state.github_login_allowlist = frozenset({"testuser"})
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    yield {"url": url, "token": token, "state": state}
    server.shutdown()


def _auth_env(
    monkeypatch: pytest.MonkeyPatch, registry_server: dict[str, Any], tmp_path: Path
) -> None:
    creds = tmp_path / "credentials"
    write_credentials(
        url=registry_server["url"],
        token=registry_server["token"],
        path=creds,
    )
    monkeypatch.setenv("BORA_REGISTRY_URL", registry_server["url"])
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", registry_server["token"])
    monkeypatch.setenv("HOME", str(tmp_path))
    # credentials load uses default path under HOME
    monkeypatch.setenv("BORA_CACHE_ROOT", str(tmp_path / "cache"))


def test_list_private_packages_with_and_without_token(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    publish_database(FIXTURE, public=False, org=TEST_ORG)
    listed = list_packages()
    assert listed["count"] >= 1
    assert any(i["database_id"] == "test/publish-min" for i in listed["items"])

    # No token: private packages filtered out.
    monkeypatch.delenv("BORA_REGISTRY_TOKEN", raising=False)
    # Force empty credentials
    empty = tmp_path / "empty-home"
    empty.mkdir()
    monkeypatch.setenv("HOME", str(empty))
    monkeypatch.setenv("BORA_REGISTRY_URL", registry_server["url"])
    listed_anon = list_packages()
    assert listed_anon["count"] == 0
    assert listed_anon["items"] == []


def test_show_matches_publish(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    summary = publish_database(FIXTURE, public=False, org=TEST_ORG)
    shown = show_package(summary["ref"])
    assert shown["package_digest"] == summary["package_digest"]
    assert shown["blob_digest"] == summary["blob_digest"]
    assert shown["size"] == summary["size"]


def test_results_upload_get_roundtrip(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    # Synthetic run dir under a copy of fixture
    db = tmp_path / "db"
    import shutil

    shutil.copytree(FIXTURE, db)
    run_id = "sha256_deadbeef_run_test1"
    run_dir = db / ".bora" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps({"task_id": "hello", "status": "PASS", "ok": True}),
        encoding="utf-8",
    )
    (run_dir / "trajectory.jsonl").write_text('{"step":1}\n', encoding="utf-8")

    up = upload_attempt_result(db, run_id=run_id)
    assert up["ok"] is True
    assert up["run_id"] == run_id

    listed = list_attempt_results(database_id="test/publish-min")
    assert listed["count"] == 1

    out = tmp_path / "restored"
    got = get_attempt_result(run_id, out_dir=out)
    assert got["ok"] is True
    restored = Path(str(got["out"]))
    assert (restored / "result.json").is_file()
    data = json.loads((restored / "result.json").read_text(encoding="utf-8"))
    assert data["status"] == "PASS"


def test_results_private_without_token_404(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    db = tmp_path / "db"
    import shutil

    shutil.copytree(FIXTURE, db)
    run_id = "sha256_cafe_run_priv"
    run_dir = db / ".bora" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text("{}", encoding="utf-8")
    upload_attempt_result(db, run_id=run_id)

    anon = RegistryClient(registry_server["url"], token=None)
    with pytest.raises(Exception) as ei:
        anon.get_attempt(run_id)
    assert "not_found" in str(ei.value) or "404" in str(ei.value)


def test_oauth_device_flow_mocked(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BORA_REGISTRY_URL", registry_server["url"])
    client = RegistryClient(registry_server["url"], token=None)

    with (
        patch(
            "services.registry.app.request_device_code",
            return_value=DeviceCodeResponse(
                device_code="dev-code",
                user_code="ABCD-1234",
                verification_uri="https://github.com/login/device",
                expires_in=900,
                interval=1,
            ),
        ),
        patch(
            "services.registry.app.poll_access_token",
            side_effect=[None, "gho_test_token"],
        ),
        patch(
            "services.registry.app.fetch_user",
            return_value=GitHubIdentity(login="testuser", id=1),
        ),
    ):
        code = client.device_code()
        assert code["user_code"] == "ABCD-1234"
        pending = client.device_poll("dev-code")
        assert pending.get("status") == "authorization_pending"
        done = client.device_poll("dev-code")
        assert "token" in done
        assert done["github_user"] == "testuser"
        assert set(done["scopes"]) == set(DEFAULT_LOGIN_SCOPES)

    # Issued token can create org + publish
    tok = done["token"]
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", tok)
    write_credentials(url=registry_server["url"], token=tok, path=tmp_path / "c")
    monkeypatch.setenv("HOME", str(tmp_path))
    _ensure_org()
    summary = publish_database(FIXTURE, public=True, org=TEST_ORG)
    assert summary["ok"] is True


def test_cache_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BORA_CACHE_ROOT", str(tmp_path / "empty-cache"))
    out = cache_list()
    assert out["count"] == 0


def test_oauth_allowlist_denies_unknown_user(
    registry_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = RegistryClient(registry_server["url"], token=None)
    with (
        patch(
            "services.registry.app.request_device_code",
            return_value=DeviceCodeResponse(
                device_code="dev-deny",
                user_code="ZZZZ-9999",
                verification_uri="https://github.com/login/device",
                expires_in=900,
                interval=1,
            ),
        ),
        patch(
            "services.registry.app.poll_access_token",
            return_value="gho_other",
        ),
        patch(
            "services.registry.app.fetch_user",
            return_value=GitHubIdentity(login="not-allowed", id=99),
        ),
    ):
        client.device_code()
        with pytest.raises(Exception) as ei:
            client.device_poll("dev-deny")
        assert "login_not_allowed" in str(ei.value) or "403" in str(ei.value)


def test_results_upload_scope_cannot_read_private(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """results:upload alone must not list/get private results."""
    state = registry_server["state"]
    upload_only = "upload-only-token-test"
    state.tokens.add(upload_only, {"results:upload"})

    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    db = tmp_path / "db-upload-scope"
    import shutil

    shutil.copytree(FIXTURE, db)
    run_id = "sha256_upload_only_run"
    run_dir = db / ".bora" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text("{}", encoding="utf-8")

    upload_attempt_result(db, run_id=run_id)

    upload_client = RegistryClient(registry_server["url"], token=upload_only)
    with pytest.raises(Exception) as ei:
        upload_client.get_attempt(run_id)
    assert "not_found" in str(ei.value) or "404" in str(ei.value)
    full = RegistryClient(registry_server["url"], token=registry_server["token"])
    meta = full.get_attempt(run_id)
    assert meta["run_id"] == run_id


def _write_suite_summary(db: Path, suite_run_id: str) -> Path:
    suite_dir = db / ".bora" / "suite-runs" / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "bora.suite.summary/1",
        "suite_run_id": suite_run_id,
        "database_id": "test/publish-min",
        "database_version": "0.1.0",
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "r1"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "run_id": "r2"},
            {"task_id": "c", "status": "PASS", "score": 1.0, "run_id": "r3"},
        ],
        "task_refs": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "r1"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "run_id": "r2"},
            {"task_id": "c", "status": "PASS", "score": 1.0, "run_id": "r3"},
        ],
        "counts": {"pass": 2, "fail": 1, "error": 0, "skipped": 0},
        "metrics": {
            "pass_rate": 2 / 3,
            "mean_score": 2 / 3,
            "n_tasks": 3,
            "n_pass": 2,
            "n_fail": 1,
            "n_error": 0,
            "missing_score_as": 0.0,
        },
        "exit_code": 1,
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return suite_dir


def test_suite_results_upload_get_list_roundtrip(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-suite"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_abc123deadbeef"
    _write_suite_summary(db, suite_run_id)

    up = upload_suite_result(
        db,
        suite_run_id=suite_run_id,
        agent_label="codex",
        model_label="gpt-test",
    )
    assert up["ok"] is True
    assert up["suite_run_id"] == suite_run_id
    assert up["pass_rate"] == pytest.approx(2 / 3)
    assert up["mean_score"] == pytest.approx(2 / 3)
    assert len(up["task_refs"]) == 3
    assert "pass" not in up or up.get("pass") is not True
    assert "suite-level PASS" in up.get("note", "") or "no suite-level PASS" in up.get("note", "")

    listed = list_suite_results(database_id="test/publish-min")
    assert listed["count"] == 1
    assert listed["items"][0]["suite_run_id"] == suite_run_id
    assert listed["items"][0]["agent_label"] == "codex"

    got = get_suite_result(suite_run_id)
    assert got["ok"] is True
    assert got["metrics"]["n_pass"] == 2
    assert got["task_refs"][0]["task_id"] == "a"

    out = tmp_path / "suite-restored"
    got_arch = get_suite_result(suite_run_id, out_dir=out)
    assert Path(str(got_arch["out"])).is_dir()
    assert (Path(str(got_arch["out"])) / "summary.json").is_file()


def test_suite_results_local_fallback(tmp_path: Path) -> None:
    import shutil

    db = tmp_path / "db-local-suite"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_local_only"
    _write_suite_summary(db, suite_run_id)

    listed = list_suite_results(local=db)
    assert listed["source"] == "local"
    assert listed["count"] == 1
    assert listed["items"][0]["pass_rate"] == pytest.approx(2 / 3)

    got = get_suite_result(suite_run_id, local=db)
    assert got["source"] == "local"
    assert got["suite_run_id"] == suite_run_id
    assert "summary_path" in got


def test_suite_results_recompute_metrics_when_missing(tmp_path: Path) -> None:
    """Older summaries without metrics still yield stable aggregates from tasks[]."""
    import shutil

    db = tmp_path / "db-legacy-suite"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_legacy_no_metrics"
    suite_dir = db / ".bora" / "suite-runs" / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "bora.suite.summary/1",
        "suite_run_id": suite_run_id,
        "database_id": "test/publish-min",
        "database_version": "0.1.0",
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "r1"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "run_id": "r2"},
            {"task_id": "c", "status": "ERROR", "score": None, "run_id": None},
        ],
        "exit_code": 2,
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    got = get_suite_result(suite_run_id, local=db)
    assert got["pass_rate"] == pytest.approx(1 / 3)
    assert got["mean_score"] == pytest.approx(1 / 3)  # 1.0 + 0.0 + 0.0
    assert len(got["task_refs"]) == 3
    assert got["metrics"]["n_error"] == 1


def test_suite_upload_scope_cannot_read_private(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Private suite results: upload-only token gets 404 on get (same as attempts)."""
    state = registry_server["state"]
    upload_only = "upload-only-suite-token"
    state.tokens.add(upload_only, {"results:upload"})
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-suite-scope"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_private_scope"
    _write_suite_summary(db, suite_run_id)
    upload_suite_result(db, suite_run_id=suite_run_id)

    upload_client = RegistryClient(registry_server["url"], token=upload_only)
    with pytest.raises(Exception) as ei:
        upload_client.get_suite(suite_run_id)
    assert "not_found" in str(ei.value) or "404" in str(ei.value)

    full = RegistryClient(registry_server["url"], token=registry_server["token"])
    meta = full.get_suite(suite_run_id)
    assert meta["suite_run_id"] == suite_run_id
    assert meta["visibility"] == "private"


def test_suite_upload_rejects_suite_pass_field(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Server must reject suite-level PASS authority fields."""
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    client = RegistryClient(registry_server["url"], token=registry_server["token"])
    # Craft a minimal valid archive
    from bora.registry.results_archive import build_suite_archive

    suite_dir = tmp_path / "suite_dir"
    suite_dir.mkdir()
    (suite_dir / "summary.json").write_text("{}", encoding="utf-8")
    archive, digest, size = build_suite_archive(suite_dir, suite_run_id="suite_bad")
    # Direct multipart with forbidden field
    import secrets as _secrets

    meta = {
        "suite_run_id": "suite_bad",
        "database_id": "test/x",
        "database_version": "0",
        "visibility": "private",
        "pass_rate": 1.0,
        "mean_score": 1.0,
        "metrics": {},
        "task_refs": [],
        "agent_label": "",
        "model_label": "",
        "exit_code": 0,
        "blob_digest": digest,
        "size": size,
        "pass": True,  # forbidden
    }
    boundary = f"bora-suite-{_secrets.token_hex(8)}"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="metadata"\r\n'
    body += b"Content-Type: application/json\r\n\r\n"
    body += json.dumps(meta).encode()
    body += b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="archive"; filename="s.tar.gz"\r\n'
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += archive
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    from bora.registry.client import RegistryError

    with pytest.raises(RegistryError) as ei:
        client._request(
            "POST",
            "/v1/results/suites",
            body=body,
            headers=client._headers(
                content_type=f"multipart/form-data; boundary={boundary}",
                auth=True,
            ),
        )
    assert ei.value.status == 400
    assert "PASS" in ei.value.message or "pass" in ei.value.message


def test_multipart_payload_trailing_lf_preserved() -> None:
    """Archive bytes ending in 0x0a must not be stripped (gzip footer risk)."""
    from services.registry.app import _parse_multipart

    archive = b"hello-archive-payload\n"
    boundary = "testbound"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n'
            "Content-Type: application/json\r\n\r\n"
            '{"k":1}\r\n'
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="archive"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + archive
        + f"\r\n--{boundary}--\r\n".encode()
    )
    parts = _parse_multipart(body, f"multipart/form-data; boundary={boundary}")
    assert parts["archive"] == archive
    assert parts["archive"].endswith(b"\n")


def _write_local_attempt(db: Path, run_id: str, *, task_id: str = "a") -> Path:
    run_dir = db / ".bora" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps({"task_id": task_id, "status": "PASS", "score": 1.0}, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "trajectory.jsonl").write_text(
        '{"type":"message","role":"assistant","content":"hi"}\n',
        encoding="utf-8",
    )
    return run_dir


def test_suite_upload_with_attempts_and_has_content_projection(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#43: --with-attempts uploads runs; suite task_refs gain has_attempt_content."""
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-with-attempts"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_with_attempts_01"
    _write_suite_summary(db, suite_run_id)
    for rid in ("r1", "r2", "r3"):
        _write_local_attempt(db, rid)

    # Suite-only: flags false
    up_summary = upload_suite_result(db, suite_run_id=suite_run_id, public=True)
    assert up_summary["ok"] is True
    assert "attempts" not in up_summary or up_summary.get("with_attempts") is not True
    listed = list_suite_results(database_id="test/publish-min")
    refs0 = listed["items"][0]["task_refs"]
    assert all(r.get("has_attempt_content") is False for r in refs0)

    # With attempts (suite already exists → conflict on re-upload suite)
    # Use a second suite id with same runs for clean suite row + attempt flags.
    suite_run_id2 = "suite_with_attempts_02"
    _write_suite_summary(db, suite_run_id2)
    up = upload_suite_result(
        db,
        suite_run_id=suite_run_id2,
        public=True,
        with_attempts=True,
    )
    assert up["ok"] is True
    assert up["with_attempts"] is True
    assert up["attempts_total"] == 3
    # First suite uploaded no attempts; second with_attempts creates them
    # (or marks existing if r1-r3 already present from a prior path).
    assert up["attempts_uploaded"] + up["attempts_existing"] == 3

    got = get_suite_result(suite_run_id2)
    assert got["ok"] is True
    for ref in got["task_refs"]:
        assert ref.get("has_attempt_content") is True
        assert ref.get("run_id")

    # Attempt meta carries suite_run_id; file list/get works
    client = RegistryClient(registry_server["url"], token=registry_server["token"])
    meta = client.get_attempt("r1")
    assert meta["run_id"] == "r1"
    assert meta.get("suite_run_id") == suite_run_id2
    status, raw, _ = client._request(
        "GET",
        "/v1/results/attempts/r1/files",
        auth=True,
    )
    assert status == 200
    files = json.loads(raw.decode("utf-8"))
    paths = {i["path"] for i in files["items"] if i.get("type") == "file"}
    assert any(p.endswith("result.json") for p in paths)
    # Read a member (path as stored in archive)
    sample = next(p for p in paths if p.endswith("result.json"))
    status2, raw2, _ = client._request(
        "GET",
        f"/v1/results/attempts/r1/files/{sample}",
        auth=True,
    )
    assert status2 == 200
    body = json.loads(raw2.decode("utf-8"))
    assert body.get("encoding") == "utf-8"
    assert "PASS" in body.get("content", "") or "task_id" in body.get("content", "")


def test_suite_with_attempts_missing_run_dir_fails_closed(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    from bora.config.errors import ConfigError

    db = tmp_path / "db-missing-runs"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_missing_runs"
    _write_suite_summary(db, suite_run_id)
    # only one of three run dirs
    _write_local_attempt(db, "r1")

    with pytest.raises(ConfigError) as ei:
        upload_suite_result(db, suite_run_id=suite_run_id, with_attempts=True)
    assert ei.value.error_code == "invalid_package"
    assert "missing local run dir" in str(ei.value).lower() or "missing" in str(ei.value).lower()
    # Suite must not have been uploaded when preflight fails
    listed = list_suite_results(database_id="test/publish-min")
    assert all(i.get("suite_run_id") != suite_run_id for i in listed["items"])


def test_attempt_upload_allow_existing_idempotent(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-idempotent"
    shutil.copytree(FIXTURE, db)
    run_id = "run_idempotent_1"
    _write_local_attempt(db, run_id)
    first = upload_attempt_result(db, run_id=run_id, public=True)
    assert first["ok"] is True
    assert first.get("already_exists") is False
    second = upload_attempt_result(db, run_id=run_id, public=True, allow_existing=True)
    assert second["ok"] is True
    assert second.get("already_exists") is True


def test_has_attempt_content_respects_attempt_visibility(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#43: private attempt must not show has_attempt_content to principals who cannot open it."""
    from bora.registry.client import RegistryError

    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-visibility-flags"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_vis_flags"
    _write_suite_summary(db, suite_run_id)
    for rid in ("r1", "r2", "r3"):
        _write_local_attempt(db, rid)
        # Private attempts; suite is public so anon can list suite summary.
        upload_attempt_result(db, run_id=rid, public=False)

    upload_suite_result(db, suite_run_id=suite_run_id, public=True)

    owner = get_suite_result(suite_run_id)
    assert owner["ok"] is True
    assert all(
        ref.get("has_attempt_content") is True
        for ref in owner["task_refs"]
        if ref.get("run_id")
    )

    anon = RegistryClient(registry_server["url"], token=None)
    items = anon.list_suites(database_id="test/publish-min")
    hit = next(i for i in items if i.get("suite_run_id") == suite_run_id)
    for ref in hit["task_refs"]:
        if ref.get("run_id"):
            assert ref.get("has_attempt_content") is False

    # Anon file browse must 404 (not leak private attempt).
    with pytest.raises(RegistryError) as ei:
        anon._request("GET", "/v1/results/attempts/r1/files", auth=False)
    assert ei.value.status == 404


def test_attempt_file_path_traversal_rejected(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bora.registry.client import RegistryError

    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    db = tmp_path / "db-path-trav"
    shutil.copytree(FIXTURE, db)
    run_id = "run_path_safe"
    _write_local_attempt(db, run_id)
    upload_attempt_result(db, run_id=run_id, public=True)

    client = RegistryClient(registry_server["url"], token=registry_server["token"])
    for bad in ("../secret", ".bora/runs/../../etc/passwd", "/etc/passwd"):
        with pytest.raises(RegistryError) as ei:
            client._request(
                "GET",
                f"/v1/results/attempts/{run_id}/files/{bad}",
                auth=True,
            )
        assert ei.value.status == 400, (bad, ei.value)
        assert ei.value.code == "invalid_path"


def test_with_attempts_rejects_traversal_run_id(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
    _ensure_org()
    import shutil

    from bora.config.errors import ConfigError

    db = tmp_path / "db-bad-runid"
    shutil.copytree(FIXTURE, db)
    suite_run_id = "suite_bad_runid"
    suite_dir = db / ".bora" / "suite-runs" / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "suite_run_id": suite_run_id,
        "database_id": "test/publish-min",
        "database_version": "0",
        "pass_rate": 1.0,
        "mean_score": 1.0,
        "metrics": {"n_pass": 1, "n_fail": 0, "n_error": 0, "n_total": 1},
        "tasks": [{"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "../escape"}],
        "exit_code": 0,
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        upload_suite_result(db, suite_run_id=suite_run_id, with_attempts=True)
    assert ei.value.error_code == "invalid_package"
