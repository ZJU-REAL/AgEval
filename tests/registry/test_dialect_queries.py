"""Dialect placeholder translation + shared query builders."""

from __future__ import annotations

from services.registry import queries as Q
from services.registry.dialect import pg_sql
from services.registry.routes import match_route


def test_pg_sql_translates_placeholders() -> None:
    assert pg_sql("SELECT * FROM t WHERE a=? AND b=?") == "SELECT * FROM t WHERE a=%s AND b=%s"
    assert "?" not in pg_sql(Q.INSERT_RELEASE)


def test_list_releases_query_public_default() -> None:
    sql, params = Q.list_releases_query()
    assert "visibility = 'public'" in sql
    assert params == []


def test_list_releases_query_private_filter() -> None:
    sql, params = Q.list_releases_query(include_private=True, visibility="private")
    assert "visibility = ?" in sql
    assert params == ["private"]
    assert "visibility = %s" in pg_sql(sql)


def test_match_route_release_draft() -> None:
    matched = match_route("POST", "/v1/packages/acme/db/release")
    assert matched is not None
    route, kwargs = matched
    assert route.name == "release_draft"
    assert kwargs["database_id"] == "acme/db"


def test_match_route_package_version_meta() -> None:
    matched = match_route("GET", "/v1/packages/acme/db/versions/1.0.0")
    assert matched is not None
    route, kwargs = matched
    assert route.name == "serve_meta"
    assert kwargs["database_id"] == "acme/db"
    assert kwargs["version"] == "1.0.0"
    assert kwargs["package_digest"] is None


def test_upsert_token_does_not_bind_created_at() -> None:
    # Live Postgres api_tokens.created_at is timestamptz; epoch floats fail.
    assert "created_at" not in Q.UPSERT_TOKEN


def test_sqlite_align_integer_flag_is_noop(tmp_path) -> None:
    from services.registry.sql_adapter import SqliteAdapter

    adapter = SqliteAdapter(tmp_path / "meta.sqlite3")
    with adapter.connect() as conn:
        adapter.align_integer_flag(conn, "organizations", "is_claimable")


def test_align_integer_flag_rejects_bad_ident() -> None:
    import pytest
    from services.registry.sql_adapter import PostgresAdapter

    fake = object.__new__(PostgresAdapter)
    with pytest.raises(ValueError, match="identifier"):
        fake.align_integer_flag(None, "organizations;drop", "is_claimable")


def test_store_has_no_sql_literals() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "services" / "registry" / "store.py").read_text(
        encoding="utf-8"
    )
    needles = ("DELETE FROM", "INSERT INTO", "CREATE TABLE", "UPDATE ")
    offenders: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(n in line for n in needles):
            offenders.append(f"{i}:{stripped}")
    assert offenders == []


def test_match_route_health_skip_auth() -> None:
    matched = match_route("GET", "/health")
    assert matched is not None
    route, _kwargs = matched
    assert route.name == "health"
    assert route.skip_auth is True
