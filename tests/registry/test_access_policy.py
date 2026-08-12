"""AccessPolicy centralizes Registry ACL decisions."""

from __future__ import annotations

from pathlib import Path

from services.registry.access import AccessPolicy
from services.registry.store import MetadataStore, ReleaseRow, TokenInfo, now


def test_visible_package_public_and_org_member(tmp_path: Path) -> None:
    meta = MetadataStore(tmp_path / "meta.sqlite")
    meta.create_org(name="acme", display_name="Acme", owner_user_id="alice")
    policy = AccessPolicy(meta=meta)
    private = ReleaseRow(
        database_id="acme/db",
        version="1.0.0",
        visibility="private",
        package_digest="sha256:" + "a" * 64,
        blob_digest="sha256:" + "b" * 64,
        size=1,
        media_type="application/gzip",
        created_at=now(),
        org_id="acme",
    )
    meta.insert(private)
    public = ReleaseRow(
        database_id="acme/pub",
        version="1.0.0",
        visibility="public",
        package_digest="sha256:" + "c" * 64,
        blob_digest="sha256:" + "d" * 64,
        size=1,
        media_type="application/gzip",
        created_at=now(),
        org_id="acme",
    )
    meta.insert(public)
    anon = TokenInfo(scopes=frozenset())
    assert policy.visible_package(public, anon) is True
    assert policy.visible_package(private, anon) is False
    member = TokenInfo(scopes=frozenset({"read"}), user_id="alice")
    assert policy.visible_package(private, member) is True
    admin = TokenInfo(scopes=frozenset({"admin"}), user_id="bob")
    assert policy.visible_package(private, admin) is True
    stranger = TokenInfo(scopes=frozenset({"read"}), user_id="carol")
    assert policy.visible_package(private, stranger) is False


def test_can_manage_package_owner_only(tmp_path: Path) -> None:
    meta = MetadataStore(tmp_path / "meta.sqlite")
    meta.create_org(name="acme", display_name="Acme", owner_user_id="alice")
    meta.add_member("acme", "dave", role="member")
    policy = AccessPolicy(meta=meta)
    row = ReleaseRow(
        database_id="acme/db",
        version="1.0.0",
        visibility="private",
        package_digest="sha256:" + "a" * 64,
        blob_digest="sha256:" + "b" * 64,
        size=1,
        media_type="application/gzip",
        created_at=now(),
        org_id="acme",
    )
    assert policy.can_manage_package(row, TokenInfo(scopes=frozenset({"read"}), user_id="alice"))
    assert not policy.can_manage_package(row, TokenInfo(scopes=frozenset({"read"}), user_id="dave"))
    assert policy.can_manage_package(row, TokenInfo(scopes=frozenset({"admin"})))


def test_org_owner_status_matrix(tmp_path: Path) -> None:
    meta = MetadataStore(tmp_path / "meta.sqlite")
    meta.create_org(name="acme", display_name="Acme", owner_user_id="alice")
    policy = AccessPolicy(meta=meta)
    assert policy.org_owner_status(org_id="missing", auth=TokenInfo(scopes=frozenset())) == (
        "not_found"
    )
    assert (
        policy.org_owner_status(
            org_id="acme", auth=TokenInfo(scopes=frozenset({"admin"}), user_id=None)
        )
        == "ok"
    )
    assert (
        policy.org_owner_status(org_id="acme", auth=TokenInfo(scopes=frozenset())) == "unauthorized"
    )
    assert (
        policy.org_owner_status(
            org_id="acme", auth=TokenInfo(scopes=frozenset({"read"}), user_id="bob")
        )
        == "forbidden"
    )
    assert (
        policy.org_owner_status(
            org_id="acme", auth=TokenInfo(scopes=frozenset({"read"}), user_id="alice")
        )
        == "ok"
    )
