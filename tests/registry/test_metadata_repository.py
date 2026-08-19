"""One metadata repository; Postgres skipped when the daemon is absent."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from services.registry.store import (
    MetadataStore,
    PostgresMetadataStore,
    PostgresTokenStore,
    ReleaseRow,
    SqliteTokenStore,
    now,
)


def _sqlite(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "meta.sqlite")


def _postgres() -> MetadataStore | None:
    url = os.environ.get("AGEVAL_REGISTRY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        psycopg = __import__("psycopg")
        psycopg.connect(url).close()
    except Exception:
        return None
    return PostgresMetadataStore(url)


@pytest.fixture(params=["sqlite", "postgres"])
def meta(request: pytest.FixtureRequest, tmp_path: Path) -> MetadataStore:
    if request.param == "sqlite":
        return _sqlite(tmp_path)
    store = _postgres()
    if store is None:
        pytest.skip("postgres daemon absent")
    return store


def test_insert_and_get_release(meta: MetadataStore) -> None:
    row = ReleaseRow(
        dataset_id="acme/db",
        version="1.0.0",
        visibility="public",
        package_digest="sha256:" + "a" * 64,
        blob_digest="sha256:" + "b" * 64,
        size=4,
        media_type="application/gzip",
        created_at=now(),
        org_id="acme",
    )
    meta.create_org(name="acme", display_name="Acme", owner_user_id="alice")
    meta.insert(row)
    got = meta.get_by_version("acme/db", "1.0.0")
    assert got is not None
    assert got.package_digest == row.package_digest
    assert got.org_id == "acme"
    listed = meta.list_releases(dataset_id_prefix="acme/")
    assert any(r.version == "1.0.0" for r in listed)


def test_postgres_store_is_thin_adapter() -> None:
    own = [
        name
        for name, val in vars(PostgresMetadataStore).items()
        if callable(val) and name not in {"__init__"}
    ]
    assert own == [], own


def test_schema_owned_by_queries() -> None:
    from services.registry import queries as Q

    creates = [s for s in Q.SCHEMA_STATEMENTS if "CREATE TABLE IF NOT EXISTS releases" in s]
    assert len(creates) == 1


def test_sqlite_token_roundtrip(tmp_path: Path) -> None:
    tokens = SqliteTokenStore(tmp_path / "tok.sqlite")
    tokens.add("secret-token", {"read", "write"}, github_user="alice")
    info = tokens.auth_for("secret-token")
    assert info.user_id == "alice"
    assert "read" in info.scopes
    assert tokens.auth_for("nope").scopes == frozenset()


def test_postgres_token_roundtrip_against_live_types() -> None:
    """Must insert into existing TIMESTAMPTZ api_tokens, not only fresh REAL tables."""
    from services.registry.envload import load_env_file

    load_env_file()
    url = os.environ.get("AGEVAL_REGISTRY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("postgres daemon absent")
    try:
        __import__("psycopg").connect(url).close()
    except Exception:
        pytest.skip("postgres daemon absent")
    tokens = PostgresTokenStore(url)
    raw = "ageval-registry-token-type-probe"
    digest = tokens.hash_token(raw)
    try:
        tokens.add(raw, {"results:read"}, github_user="probe")
        info = tokens.auth_for(raw)
        assert info.user_id == "probe"
        assert "results:read" in info.scopes
    finally:
        with tokens._connect() as conn:
            tokens._exec(conn, "DELETE FROM api_tokens WHERE token_hash=?", (digest,))
            conn.commit()
