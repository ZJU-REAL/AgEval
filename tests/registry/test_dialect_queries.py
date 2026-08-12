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


def test_match_route_package_version_meta() -> None:
    matched = match_route("GET", "/v1/packages/acme/db/versions/1.0.0")
    assert matched is not None
    route, kwargs = matched
    assert route.name == "serve_meta"
    assert kwargs["database_id"] == "acme/db"
    assert kwargs["version"] == "1.0.0"
    assert kwargs["package_digest"] is None


def test_match_route_health_skip_auth() -> None:
    matched = match_route("GET", "/health")
    assert matched is not None
    route, _kwargs = matched
    assert route.name == "health"
    assert route.skip_auth is True
