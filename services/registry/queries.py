"""Shared SQL text for Registry metadata stores (SQLite ``?`` placeholders).

Postgres adapters run these through :func:`services.registry.dialect.pg_sql`
before execute. DDL lives here once; dialect adapters only connect / placeholder.
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

SELECT_RELEASE_BY_VERSION = "SELECT * FROM releases WHERE database_id=? AND version=?"

SELECT_RELEASE_BY_DIGEST = "SELECT * FROM releases WHERE database_id=? AND package_digest=?"


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

SELECT_MEMBERSHIP = "SELECT * FROM org_memberships WHERE org_id=? AND user_id=?"

SELECT_USER_ORG_IDS = "SELECT org_id FROM org_memberships WHERE user_id=?"

# Types chosen so SQLite and Postgres accept the same CREATE TABLE text.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS releases (
        database_id TEXT NOT NULL,
        version TEXT NOT NULL,
        visibility TEXT NOT NULL,
        package_digest TEXT NOT NULL,
        blob_digest TEXT NOT NULL,
        size INTEGER NOT NULL,
        media_type TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (database_id, version)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_digest
    ON releases(database_id, package_digest)
    """,
    """
    CREATE TABLE IF NOT EXISTS attempt_results (
        run_id TEXT PRIMARY KEY,
        database_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        lock_digest TEXT NOT NULL,
        status TEXT NOT NULL,
        visibility TEXT NOT NULL,
        blob_digest TEXT NOT NULL,
        size INTEGER NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS suite_results (
        suite_run_id TEXT PRIMARY KEY,
        database_id TEXT NOT NULL,
        database_version TEXT NOT NULL,
        visibility TEXT NOT NULL,
        pass_rate REAL NOT NULL,
        mean_score REAL NOT NULL,
        metrics_json TEXT NOT NULL,
        tasks_json TEXT NOT NULL,
        agent_label TEXT NOT NULL DEFAULT '',
        model_label TEXT NOT NULL DEFAULT '',
        blob_digest TEXT NOT NULL,
        size INTEGER NOT NULL,
        exit_code INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        config_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        org_id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        is_claimable INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_memberships (
        org_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (org_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS result_shares (
        result_kind TEXT NOT NULL,
        result_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (result_kind, result_id, target_type, target_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL DEFAULT '',
        avatar_url TEXT NOT NULL DEFAULT '',
        github_id TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_invite_keys (
        key_id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        token_prefix TEXT NOT NULL,
        created_by TEXT NOT NULL DEFAULT '',
        max_uses INTEGER,
        use_count INTEGER NOT NULL DEFAULT 0,
        expires_at REAL,
        revoked_at REAL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_tokens (
        token_hash TEXT PRIMARY KEY,
        scopes TEXT NOT NULL,
        github_user TEXT,
        created_at REAL NOT NULL,
        revoked_at REAL
    )
    """,
)

# (table, column, sqlite/postgres-compatible type clause)
SCHEMA_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("suite_results", "config_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("releases", "org_id", "TEXT"),
    ("attempt_results", "uploaded_by", "TEXT NOT NULL DEFAULT ''"),
    ("attempt_results", "suite_run_id", "TEXT NOT NULL DEFAULT ''"),
    ("suite_results", "uploaded_by", "TEXT NOT NULL DEFAULT ''"),
)

UPSERT_TOKEN = """
INSERT INTO api_tokens(token_hash, scopes, github_user, created_at, revoked_at)
VALUES (?, ?, ?, ?, NULL)
ON CONFLICT(token_hash) DO UPDATE SET
    scopes=excluded.scopes,
    github_user=excluded.github_user,
    revoked_at=NULL
"""

SELECT_TOKEN = "SELECT scopes, github_user, revoked_at FROM api_tokens WHERE token_hash=?"
