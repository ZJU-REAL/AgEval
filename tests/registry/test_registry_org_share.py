"""Org membership, package org binding, result uploaded_by + share (#52/#53/#54)."""

from __future__ import annotations

import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler
from services.registry.store import DEFAULT_LOGIN_SCOPES

from bora.application.publish_command import publish_database
from bora.application.results_command import list_attempt_results, upload_attempt_result
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import write_credentials

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "databases" / "publish-min"


@pytest.fixture()
def registry_server(tmp_path: Path):
    data = tmp_path / "reg-data"
    state, token = build_default_state(data, bootstrap_token="boot-token", memory_blob=True)
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield {"url": url, "token": token, "state": state}
    server.shutdown()


def _user_token(state, *, user: str, scopes=DEFAULT_LOGIN_SCOPES) -> str:
    raw = f"tok-{user}"
    state.tokens.add(raw, scopes, github_user=user)
    return raw


def test_org_create_list_and_publish_requires_org(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = registry_server["url"]
    boot = RegistryClient(url, token=registry_server["token"])
    org = boot.create_org(name="acme", display_name="Acme Lab")
    assert org["org_id"] == "acme"
    listed = boot.list_orgs()
    assert any(i["org_id"] == "acme" for i in listed["items"])

    write_credentials(url=url, token=registry_server["token"], path=tmp_path / "c")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BORA_REGISTRY_URL", url)
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", registry_server["token"])

    with pytest.raises(Exception) as ei:
        publish_database(FIXTURE, public=False)
    assert "org" in str(ei.value).lower()

    summary = publish_database(FIXTURE, public=False, org="acme")
    assert summary["ok"] is True
    assert summary["org_id"] == "acme"

    meta = boot.get_metadata(database_id=summary["database_id"], version=summary["version"])
    assert meta.org_id == "acme"


def test_private_package_visible_to_org_member_only(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = registry_server["state"]
    url = registry_server["url"]
    boot = RegistryClient(url, token=registry_server["token"])
    boot.create_org(name="lab")

    alice_tok = _user_token(state, user="alice")
    bob_tok = _user_token(state, user="bob")
    # bootstrap owner adds alice
    boot.add_org_member(org_id="lab", user_id="alice", role="member")

    write_credentials(url=url, token=alice_tok, path=tmp_path / "c")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BORA_REGISTRY_URL", url)
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", alice_tok)
    summary = publish_database(FIXTURE, public=False, org="lab")

    alice = RegistryClient(url, token=alice_tok)
    alice.get_metadata(database_id=summary["database_id"], version=summary["version"])

    bob = RegistryClient(url, token=bob_tok)
    with pytest.raises(RegistryError) as ei:
        bob.get_metadata(database_id=summary["database_id"], version=summary["version"])
    assert ei.value.status == 404


def test_result_uploaded_by_and_share_org(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = registry_server["state"]
    url = registry_server["url"]
    boot = RegistryClient(url, token=registry_server["token"])
    boot.create_org(name="sharelab")

    alice_tok = _user_token(state, user="alice")
    bob_tok = _user_token(state, user="bob")
    boot.add_org_member(org_id="sharelab", user_id="bob", role="member")

    db = tmp_path / "db"
    shutil.copytree(FIXTURE, db)
    run_id = "sha256_share_run1"
    run_dir = db / ".bora" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps({"task_id": "hello", "status": "PASS"}),
        encoding="utf-8",
    )

    write_credentials(url=url, token=alice_tok, path=tmp_path / "c")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BORA_REGISTRY_URL", url)
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", alice_tok)

    up = upload_attempt_result(db, run_id=run_id, public=False)
    assert up["ok"] is True
    meta = RegistryClient(url, token=alice_tok).get_attempt(run_id)
    assert meta.get("uploaded_by") == "alice"

    # bob cannot see private unshared result
    with pytest.raises(RegistryError) as ei:
        RegistryClient(url, token=bob_tok).get_attempt(run_id)
    assert ei.value.status == 404

    # alice shares to org; bob is member → can read
    RegistryClient(url, token=alice_tok).share_result(
        result_kind="attempt",
        result_id=run_id,
        target_type="org",
        target_id="sharelab",
    )
    bob_meta = RegistryClient(url, token=bob_tok).get_attempt(run_id)
    assert bob_meta["run_id"] == run_id

    # unshare → bob loses access
    RegistryClient(url, token=alice_tok).unshare_result(
        result_kind="attempt",
        result_id=run_id,
        target_type="org",
        target_id="sharelab",
    )
    with pytest.raises(RegistryError) as ei2:
        RegistryClient(url, token=bob_tok).get_attempt(run_id)
    assert ei2.value.status == 404

    # non-owner cannot share
    with pytest.raises(RegistryError):
        RegistryClient(url, token=bob_tok).share_result(
            result_kind="attempt",
            result_id=run_id,
            target_type="user",
            target_id="bob",
        )

    # list does not leak to bob
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", bob_tok)
    listed = list_attempt_results(database_id="test/publish-min")
    assert listed["count"] == 0
