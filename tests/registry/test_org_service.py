"""OrgService owns member visibility (not a Handler parallel if)."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.registry.access import AccessPolicy
from services.registry.errors import RegistryAppError
from services.registry.org_service import OrgService
from services.registry.store import MetadataStore, TokenInfo


def _orgs(tmp_path: Path) -> OrgService:
    meta = MetadataStore(tmp_path / "meta.sqlite3")
    return OrgService(meta, AccessPolicy(meta=meta))


def test_list_members_hides_org_from_outsiders(tmp_path: Path) -> None:
    svc = _orgs(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    outsider = TokenInfo(scopes=frozenset({"results:read"}), user_id="bob")
    with pytest.raises(RegistryAppError) as ei:
        svc.list_members(org_id="acme", auth=outsider)
    assert ei.value.http_status == 404
    assert ei.value.error == "not_found"


def test_list_members_visible_to_member(tmp_path: Path) -> None:
    svc = _orgs(tmp_path)
    svc.meta.create_org(name="acme", owner_user_id="alice", display_name="Acme")
    owner = TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice")
    payload = svc.list_members(org_id="acme", auth=owner)
    assert payload["org_id"] == "acme"
    assert any(item["user_id"] == "alice" for item in payload["items"])


def _user(*, admin: bool = False, user_id: str = "alice") -> TokenInfo:
    scopes = frozenset({"admin"}) if admin else frozenset({"registry:publish"})
    return TokenInfo(scopes=scopes, user_id=user_id)


def test_non_admin_cannot_create_official_org(tmp_path: Path) -> None:
    svc = _orgs(tmp_path)
    with pytest.raises(RegistryAppError) as ei:
        svc.create(name="official", display_name="Official", is_claimable=False, auth=_user())
    assert ei.value.http_status == 403
    assert ei.value.error == "forbidden"


def test_admin_creates_official_org_not_claimable(tmp_path: Path) -> None:
    svc = _orgs(tmp_path)
    payload = svc.create(
        name="Official",
        display_name="Official",
        is_claimable=True,
        auth=_user(admin=True, user_id="bootstrap"),
    )
    assert payload["org_id"] == "official"
    assert payload["is_claimable"] is False


def test_official_org_cannot_be_claimed(tmp_path: Path) -> None:
    svc = _orgs(tmp_path)
    svc.meta.create_org(
        name="official",
        owner_user_id="bootstrap",
        display_name="Official",
        is_claimable=True,
    )
    with pytest.raises(RegistryAppError) as ei:
        svc.claim(org_id="official", auth=_user())
    assert ei.value.http_status == 403
    assert "cannot claim" in ei.value.message
