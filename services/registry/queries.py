"""Shared SQL text for Registry metadata stores (SQLite ``?`` placeholders).

Postgres adapters run these through :func:`services.registry.dialect.pg_sql`
before execute. Schema DDL stays in each store (type differences).
"""

from __future__ import annotations

from typing import Any

# ---- releases --------------------------------------------------------------

INSERT_RELEASE = """
INSERT INTO releases(
    database_id, version, visibility, package_digest,
    blob_digest, size, media_type, created_at, org_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_RELEASE_BY_VERSION = (
    "SELECT * FROM releases WHERE database_id=? AND version=?"
)

SELECT_RELEASE_BY_DIGEST = (
    "SELECT * FROM releases WHERE database_id=? AND package_digest=?"
)


def list_releases_query(
    *,
    database_id_prefix: str | None = None,
    visibility: str | None = None,
    version: str | None = None,
    include_private: bool = False,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_private:
        clauses.append("visibility = 'public'")
    elif visibility in {"public", "private"}:
        clauses.append("visibility = ?")
        params.append(visibility)
    if database_id_prefix:
        clauses.append("database_id LIKE ?")
        params.append(f"{database_id_prefix}%")
    if version:
        clauses.append("version = ?")
        params.append(version)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM releases {where} ORDER BY database_id, version"
    return sql, params


def list_versions_query(
    database_id: str, *, include_private: bool = False
) -> tuple[str, list[Any]]:
    clauses = ["database_id = ?"]
    params: list[Any] = [database_id]
    if not include_private:
        clauses.append("visibility = 'public'")
    where = " AND ".join(clauses)
    return f"SELECT * FROM releases WHERE {where} ORDER BY version", params


# ---- attempt / suite results -----------------------------------------------

INSERT_ATTEMPT = """
INSERT INTO attempt_results(
    run_id, database_id, task_id, lock_digest, status,
    visibility, blob_digest, size, created_at, uploaded_by,
    suite_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_ATTEMPT = "SELECT * FROM attempt_results WHERE run_id=?"

INSERT_SUITE = """
INSERT INTO suite_results(
    suite_run_id, database_id, database_version, visibility,
    pass_rate, mean_score, metrics_json, tasks_json,
    agent_label, model_label, blob_digest, size,
    exit_code, created_at, config_json, uploaded_by
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_SUITE = "SELECT * FROM suite_results WHERE suite_run_id=?"

# ---- orgs ------------------------------------------------------------------

INSERT_ORG = """
INSERT INTO organizations(
    org_id, name, display_name, is_claimable, created_at
) VALUES (?, ?, ?, ?, ?)
"""

INSERT_ORG_OWNER_MEMBERSHIP = """
INSERT INTO org_memberships(org_id, user_id, role, created_at)
VALUES (?, ?, 'owner', ?)
"""

SELECT_ORG = "SELECT * FROM organizations WHERE org_id=?"

SELECT_MEMBERSHIP = (
    "SELECT * FROM org_memberships WHERE org_id=? AND user_id=?"
)

SELECT_USER_ORG_IDS = "SELECT org_id FROM org_memberships WHERE user_id=?"
