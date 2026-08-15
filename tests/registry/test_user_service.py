"""Public user GET: official is Registry-computed; private orgs stay hidden."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler
from services.registry.errors import RegistryAppError
from services.registry.store import MetadataStore
from services.registry.user_service import UserService


def _users(tmp_path: Path) -> UserService:
    return UserService(MetadataStore(tmp_path / "meta.sqlite3"))


def test_official_member_is_marked(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    svc.meta.create_org(name="official", owner_user_id="alice", display_name="Official")
    svc.meta.upsert_user_profile(
        user_id="Alice",
        display_name="Alice Chen",
        avatar_url="https://example.test/a.png",
    )
    payload = svc.get_public("Alice")
    assert payload["user_id"] == "alice"
    assert payload["display_name"] == "Alice Chen"
    assert payload["avatar_url"] == "https://example.test/a.png"
    assert payload["official"] is True
    assert payload["official_orgs"] == [
        {"org_id": "official", "display_name": "Official", "official": True}
    ]


def test_unofficial_member_has_no_user_mark(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    svc.meta.upsert_user_profile(user_id="alice", display_name="Alice")
    payload = svc.get_public("alice")
    assert payload["official"] is False
    assert payload["official_orgs"] == []


def test_public_payload_lists_only_official_orgs(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    svc.meta.create_org(name="official", owner_user_id="bootstrap", display_name="Official")
    svc.meta.add_member("official", "alice", role="member")
    payload = svc.get_public("alice")
    assert payload["official"] is True
    assert [row["org_id"] for row in payload["official_orgs"]] == ["official"]


def test_admin_added_never_logged_in_still_200(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    svc.meta.create_org(name="official", owner_user_id="bootstrap", display_name="Official")
    svc.meta.add_member("official", "bob", role="member")
    payload = svc.get_public("bob")
    assert payload["user_id"] == "bob"
    assert payload["official"] is True
    assert payload["display_name"] == ""
    assert payload["avatar_url"] == ""


def test_profile_without_membership_is_not_official(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    svc.meta.upsert_user_profile(user_id="solo", display_name="Solo")
    payload = svc.get_public("solo")
    assert payload["official"] is False
    assert payload["official_orgs"] == []
    assert payload["display_name"] == "Solo"


def test_unknown_login_is_not_found(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    with pytest.raises(RegistryAppError) as ei:
        svc.get_public("missing")
    assert ei.value.http_status == 404
    assert ei.value.error == "not_found"


def test_empty_user_id_is_invalid(tmp_path: Path) -> None:
    svc = _users(tmp_path)
    with pytest.raises(RegistryAppError) as ei:
        svc.get_public("   ")
    assert ei.value.http_status == 400


def test_get_user_http_is_public(tmp_path: Path) -> None:
    state, _token = build_default_state(
        tmp_path / "reg", bootstrap_token="admin-tok", memory_blob=True
    )
    state.meta.create_org(name="official", owner_user_id="alice", display_name="Official")
    state.meta.upsert_user_profile(user_id="alice", display_name="Alice")
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/v1/users/Alice")
        resp = conn.getresponse()
        payload = json.loads(resp.read().decode("utf-8"))
        conn.close()
        assert resp.status == 200
        assert payload["user_id"] == "alice"
        assert payload["official"] is True

        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/v1/users/nobody")
        resp = conn.getresponse()
        missing = json.loads(resp.read().decode("utf-8"))
        conn.close()
        assert resp.status == 404
        assert missing["error"] == "not_found"
    finally:
        server.shutdown()
        server.server_close()
