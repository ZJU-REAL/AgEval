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
