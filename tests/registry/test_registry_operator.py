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
    list_attempt_results,
    upload_attempt_result,
)
from bora.registry.client import RegistryClient
from bora.registry.credentials import write_credentials

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"


@pytest.fixture()
def registry_server(tmp_path: Path):
    data = tmp_path / "reg-data"
    state, token = build_default_state(data, bootstrap_token="test-token-publish", memory_blob=True)
    # Enable OAuth config for login tests (mocked GitHub).
    state.github_client_id = "test-client-id"
    state.github_client_secret = "test-client-secret"
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
    publish_database(FIXTURE, public=False)
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
    summary = publish_database(FIXTURE, public=False)
    shown = show_package(summary["ref"])
    assert shown["package_digest"] == summary["package_digest"]
    assert shown["blob_digest"] == summary["blob_digest"]
    assert shown["size"] == summary["size"]


def test_results_upload_get_roundtrip(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth_env(monkeypatch, registry_server, tmp_path)
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

    # Issued token can publish
    tok = done["token"]
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", tok)
    write_credentials(url=registry_server["url"], token=tok, path=tmp_path / "c")
    monkeypatch.setenv("HOME", str(tmp_path))
    summary = publish_database(FIXTURE, public=True)
    assert summary["ok"] is True


def test_cache_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BORA_CACHE_ROOT", str(tmp_path / "empty-cache"))
    out = cache_list()
    assert out["count"] == 0
