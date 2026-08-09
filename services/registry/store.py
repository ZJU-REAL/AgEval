"""Registry metadata, tokens, results, and blob storage.

Unit tests: SQLite + Memory blob.
Compose / production: Postgres + S3-compatible (RustFS).

Raw API tokens are never persisted — only sha256 digests.
Visibility is only ``public`` | ``private``.
Packages require ``org_id`` on new publishes; results carry ``uploaded_by``
and optional share targets (org / user). Private read is ownership/membership
based (admin bypass); scopes alone no longer grant global private sight.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReleaseRow:
    database_id: str
    version: str
    visibility: str
    package_digest: str
    blob_digest: str
    size: int
    media_type: str
    created_at: float
    org_id: str | None = None


@dataclass(frozen=True, slots=True)
class AttemptResultRow:
    """Sealed Attempt evidence bundle metadata (not a Database package)."""

    run_id: str
    database_id: str
    task_id: str
    lock_digest: str
    status: str
    visibility: str
    blob_digest: str
    size: int
    created_at: float
    uploaded_by: str = ""


@dataclass(frozen=True, slots=True)
class SuiteResultRow:
    """Suite/job result row: aggregates + per-task refs (not suite PASS).

    Observational leaderboard input for Hub SPA (#22 S5). PASS remains
    per-task evaluator only.
    """

    suite_run_id: str
    database_id: str
    database_version: str
    visibility: str
    pass_rate: float
    mean_score: float
    metrics_json: str
    tasks_json: str
    agent_label: str
    model_label: str
    blob_digest: str
    size: int
    exit_code: int
    created_at: float
    # #42 config comparability (optional; empty/default on legacy rows)
    config_json: str = "{}"
    uploaded_by: str = ""


@dataclass(frozen=True, slots=True)
class OrgRow:
    org_id: str
    name: str
    display_name: str
    is_claimable: bool
    created_at: float


@dataclass(frozen=True, slots=True)
class MembershipRow:
    org_id: str
    user_id: str
    role: str
    created_at: float


@dataclass(frozen=True, slots=True)
class TokenInfo:
    """Resolved bearer token: scopes + optional user identity (github login)."""

    scopes: frozenset[str]
    user_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResultShareRow:
    result_kind: str  # attempt | suite
    result_id: str
    target_type: str  # org | user
    target_id: str
    created_at: float


# ---------------------------------------------------------------------------
# Blob
# ---------------------------------------------------------------------------


class MemoryBlobStore:
    """Unit-test only blob backend."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def _key(self, blob_digest: str, prefix: str) -> str:
        return f"{prefix}/{blob_digest}"

    def put_if_absent(self, blob_digest: str, data: bytes, *, prefix: str = "packages") -> None:
        with self._lock:
            self._data.setdefault(self._key(blob_digest, prefix), data)

    def get(self, blob_digest: str, *, prefix: str = "packages") -> bytes | None:
        with self._lock:
            return self._data.get(self._key(blob_digest, prefix))


class FilesystemBlobStore:
    """Dev fallback: local directory. Prefer S3 for compose e2e."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, blob_digest: str, prefix: str) -> Path:
        key = blob_digest.replace(":", "_")
        return self.root / prefix / key

    def put_if_absent(self, blob_digest: str, data: bytes, *, prefix: str = "packages") -> None:
        path = self._path(blob_digest, prefix)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, blob_digest: str, *, prefix: str = "packages") -> bytes | None:
        path = self._path(blob_digest, prefix)
        if not path.is_file():
            return None
        return path.read_bytes()


class S3BlobStore:
    """S3-compatible blob store (RustFS / AWS). Credentials stay server-side only."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        try:
            import boto3
            from botocore.client import Config
            from botocore.exceptions import ClientError
        except ImportError as exc:
            raise RuntimeError(
                "boto3 required for S3 blob backend; install with: uv sync --extra registry"
            ) from exc
        self._ClientError = ClientError
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint.rstrip("/"),
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        import contextlib

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except self._ClientError:
            with contextlib.suppress(self._ClientError):
                self._client.create_bucket(Bucket=self.bucket)

    def _object_key(self, blob_digest: str, prefix: str) -> str:
        return f"{prefix}/{blob_digest.replace(':', '_')}"

    def put_if_absent(self, blob_digest: str, data: bytes, *, prefix: str = "packages") -> None:
        key = self._object_key(blob_digest, prefix)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return
        except self._ClientError:
            pass
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, blob_digest: str, *, prefix: str = "packages") -> bytes | None:
        key = self._object_key(blob_digest, prefix)
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
        except self._ClientError:
            return None
        return bytes(resp["Body"].read())


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


DEFAULT_LOGIN_SCOPES: frozenset[str] = frozenset(
    {
        "registry:publish",
        "read-private",
        "results:upload",
        "results:read",
    }
)

ADMIN_SCOPES: frozenset[str] = frozenset(
    {
        "admin",
        "registry:publish",
        "read-private",
        "results:upload",
        "results:read",
    }
)


def _normalize_user_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    u = str(raw).strip()
    if not u:
        return None
    return u.casefold()


class TokenStore:
    """In-memory tokens (tests). Prefer SqliteTokenStore / PostgresTokenStore."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, TokenInfo] = {}

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add(
        self,
        raw_token: str,
        scopes: set[str] | frozenset[str],
        *,
        github_user: str | None = None,
    ) -> None:
        with self._lock:
            self._tokens[self.hash_token(raw_token)] = TokenInfo(
                scopes=frozenset(scopes),
                user_id=_normalize_user_id(github_user),
            )

    def auth_for(self, raw_token: str | None) -> TokenInfo:
        if not raw_token:
            return TokenInfo(scopes=frozenset())
        with self._lock:
            return self._tokens.get(self.hash_token(raw_token), TokenInfo(scopes=frozenset()))

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        return self.auth_for(raw_token).scopes


class SqliteTokenStore:
    """Persistent tokens in the same SQLite file as metadata (unit / zero-dep)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token_hash TEXT PRIMARY KEY,
                    scopes TEXT NOT NULL,
                    github_user TEXT,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                )
                """
            )
            conn.commit()

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add(
        self,
        raw_token: str,
        scopes: set[str] | frozenset[str],
        *,
        github_user: str | None = None,
    ) -> None:
        scopes_json = json.dumps(sorted(scopes))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO api_tokens(
                    token_hash, scopes, github_user, created_at, revoked_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (self.hash_token(raw_token), scopes_json, github_user, time.time()),
            )
            conn.commit()

    def auth_for(self, raw_token: str | None) -> TokenInfo:
        if not raw_token:
            return TokenInfo(scopes=frozenset())
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT scopes, github_user, revoked_at FROM api_tokens WHERE token_hash=?",
                (self.hash_token(raw_token),),
            )
            row = cur.fetchone()
            if row is None or row["revoked_at"] is not None:
                return TokenInfo(scopes=frozenset())
            try:
                data = json.loads(row["scopes"])
            except json.JSONDecodeError:
                return TokenInfo(scopes=frozenset())
            return TokenInfo(
                scopes=frozenset(str(s) for s in data),
                user_id=_normalize_user_id(row["github_user"]),
            )

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        return self.auth_for(raw_token).scopes


class PostgresTokenStore:
    """Persistent tokens in Postgres."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg required for Postgres backend; install with: uv sync --extra registry"
            ) from exc
        self._psycopg = psycopg
        self.database_url = database_url
        self._init()

    def _connect(self):  # noqa: ANN202
        return self._psycopg.connect(self.database_url)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token_hash TEXT PRIMARY KEY,
                    scopes JSONB NOT NULL,
                    github_user TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    revoked_at TIMESTAMPTZ
                )
                """
            )
            conn.commit()

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add(
        self,
        raw_token: str,
        scopes: set[str] | frozenset[str],
        *,
        github_user: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_tokens(token_hash, scopes, github_user)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (token_hash) DO UPDATE
                  SET scopes = EXCLUDED.scopes,
                      github_user = EXCLUDED.github_user,
                      revoked_at = NULL
                """,
                (self.hash_token(raw_token), json.dumps(sorted(scopes)), github_user),
            )
            conn.commit()

    def auth_for(self, raw_token: str | None) -> TokenInfo:
        if not raw_token:
            return TokenInfo(scopes=frozenset())
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT scopes, github_user FROM api_tokens
                WHERE token_hash = %s AND revoked_at IS NULL
                """,
                (self.hash_token(raw_token),),
            )
            row = cur.fetchone()
            if row is None:
                return TokenInfo(scopes=frozenset())
            scopes_raw = row[0]
            if isinstance(scopes_raw, list):
                scopes = frozenset(str(s) for s in scopes_raw)
            elif isinstance(scopes_raw, str):
                scopes = frozenset(str(s) for s in json.loads(scopes_raw))
            else:
                scopes = frozenset()
            return TokenInfo(scopes=scopes, user_id=_normalize_user_id(row[1]))

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        return self.auth_for(raw_token).scopes


# ---------------------------------------------------------------------------
# Metadata (packages + attempt results + orgs + shares)
# ---------------------------------------------------------------------------


class MetadataStore:
    """SQLite release + attempt_results metadata (unit tests / zero-dep)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
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
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_digest
                ON releases(database_id, package_digest)
                """
            )
            conn.execute(
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
                """
            )
            conn.execute(
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
                """
            )
            # Migrate pre-#42 DBs: add config_json if missing.
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(suite_results)").fetchall()}
            if "config_json" not in cols:
                conn.execute(
                    "ALTER TABLE suite_results ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}'"
                )
            # Org + ACL columns (#52 / #53 / #54)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    org_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    is_claimable INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS org_memberships (
                    org_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (org_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS result_shares (
                    result_kind TEXT NOT NULL,
                    result_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (result_kind, result_id, target_type, target_id)
                )
                """
            )
            rel_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(releases)").fetchall()}
            if "org_id" not in rel_cols:
                conn.execute("ALTER TABLE releases ADD COLUMN org_id TEXT")
            att_cols = {
                str(r[1]) for r in conn.execute("PRAGMA table_info(attempt_results)").fetchall()
            }
            if "uploaded_by" not in att_cols:
                conn.execute(
                    "ALTER TABLE attempt_results ADD COLUMN uploaded_by TEXT NOT NULL DEFAULT ''"
                )
            suite_cols = {
                str(r[1]) for r in conn.execute("PRAGMA table_info(suite_results)").fetchall()
            }
            if "uploaded_by" not in suite_cols:
                conn.execute(
                    "ALTER TABLE suite_results ADD COLUMN uploaded_by TEXT NOT NULL DEFAULT ''"
                )
            conn.commit()

    def insert(self, row: ReleaseRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO releases(
                        database_id, version, visibility, package_digest,
                        blob_digest, size, media_type, created_at, org_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.database_id,
                        row.version,
                        row.visibility,
                        row.package_digest,
                        row.blob_digest,
                        row.size,
                        row.media_type,
                        row.created_at,
                        row.org_id,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("release already exists") from exc

    def get_by_version(self, database_id: str, version: str) -> ReleaseRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM releases WHERE database_id=? AND version=?",
                (database_id, version),
            )
            r = cur.fetchone()
            return self._release_row(r) if r else None

    def get_by_digest(self, database_id: str, package_digest: str) -> ReleaseRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM releases WHERE database_id=? AND package_digest=?",
                (database_id, package_digest),
            )
            r = cur.fetchone()
            return self._release_row(r) if r else None

    def list_releases(
        self,
        *,
        database_id_prefix: str | None = None,
        visibility: str | None = None,
        version: str | None = None,
        include_private: bool = False,
    ) -> list[ReleaseRow]:
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
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return [self._release_row(r) for r in cur.fetchall()]

    def list_versions(self, database_id: str, *, include_private: bool = False) -> list[ReleaseRow]:
        clauses = ["database_id = ?"]
        params: list[Any] = [database_id]
        if not include_private:
            clauses.append("visibility = 'public'")
        where = " AND ".join(clauses)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM releases WHERE {where} ORDER BY version",
                params,
            )
            return [self._release_row(r) for r in cur.fetchall()]

    def insert_attempt(self, row: AttemptResultRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO attempt_results(
                        run_id, database_id, task_id, lock_digest, status,
                        visibility, blob_digest, size, created_at, uploaded_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.run_id,
                        row.database_id,
                        row.task_id,
                        row.lock_digest,
                        row.status,
                        row.visibility,
                        row.blob_digest,
                        row.size,
                        row.created_at,
                        row.uploaded_by or "",
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("attempt result already exists") from exc

    def get_attempt(self, run_id: str) -> AttemptResultRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM attempt_results WHERE run_id=?",
                (run_id,),
            )
            r = cur.fetchone()
            return self._attempt_row(r) if r else None

    def list_attempts(
        self,
        *,
        database_id: str | None = None,
        include_private: bool = False,
    ) -> list[AttemptResultRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_private:
            clauses.append("visibility = 'public'")
        if database_id:
            clauses.append("database_id = ?")
            params.append(database_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM attempt_results {where} ORDER BY created_at DESC",
                params,
            )
            return [self._attempt_row(r) for r in cur.fetchall()]

    def insert_suite(self, row: SuiteResultRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO suite_results(
                        suite_run_id, database_id, database_version, visibility,
                        pass_rate, mean_score, metrics_json, tasks_json,
                        agent_label, model_label, blob_digest, size,
                        exit_code, created_at, config_json, uploaded_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.suite_run_id,
                        row.database_id,
                        row.database_version,
                        row.visibility,
                        row.pass_rate,
                        row.mean_score,
                        row.metrics_json,
                        row.tasks_json,
                        row.agent_label,
                        row.model_label,
                        row.blob_digest,
                        row.size,
                        row.exit_code,
                        row.created_at,
                        row.config_json or "{}",
                        row.uploaded_by or "",
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("suite result already exists") from exc

    def get_suite(self, suite_run_id: str) -> SuiteResultRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM suite_results WHERE suite_run_id=?",
                (suite_run_id,),
            )
            r = cur.fetchone()
            return self._suite_row(r) if r else None

    def list_suites(
        self,
        *,
        database_id: str | None = None,
        include_private: bool = False,
    ) -> list[SuiteResultRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_private:
            clauses.append("visibility = 'public'")
        if database_id:
            clauses.append("database_id = ?")
            params.append(database_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM suite_results {where} ORDER BY created_at DESC",
                params,
            )
            return [self._suite_row(r) for r in cur.fetchall()]

    @staticmethod
    def _release_row(r: sqlite3.Row) -> ReleaseRow:
        keys = r.keys()
        org_id = r["org_id"] if "org_id" in keys else None
        return ReleaseRow(
            database_id=r["database_id"],
            version=r["version"],
            visibility=r["visibility"],
            package_digest=r["package_digest"],
            blob_digest=r["blob_digest"],
            size=int(r["size"]),
            media_type=r["media_type"],
            created_at=float(r["created_at"]),
            org_id=str(org_id) if org_id else None,
        )

    @staticmethod
    def _attempt_row(r: sqlite3.Row) -> AttemptResultRow:
        keys = r.keys()
        uploaded_by = str(r["uploaded_by"]) if "uploaded_by" in keys and r["uploaded_by"] else ""
        return AttemptResultRow(
            run_id=r["run_id"],
            database_id=r["database_id"],
            task_id=r["task_id"],
            lock_digest=r["lock_digest"],
            status=r["status"],
            visibility=r["visibility"],
            blob_digest=r["blob_digest"],
            size=int(r["size"]),
            created_at=float(r["created_at"]),
            uploaded_by=uploaded_by,
        )

    @staticmethod
    def _suite_row(r: sqlite3.Row) -> SuiteResultRow:
        keys = r.keys()
        config_json = str(r["config_json"]) if "config_json" in keys and r["config_json"] else "{}"
        uploaded_by = str(r["uploaded_by"]) if "uploaded_by" in keys and r["uploaded_by"] else ""
        return SuiteResultRow(
            suite_run_id=r["suite_run_id"],
            database_id=r["database_id"],
            database_version=r["database_version"],
            visibility=r["visibility"],
            pass_rate=float(r["pass_rate"]),
            mean_score=float(r["mean_score"]),
            metrics_json=str(r["metrics_json"]),
            tasks_json=str(r["tasks_json"]),
            agent_label=str(r["agent_label"] or ""),
            model_label=str(r["model_label"] or ""),
            blob_digest=r["blob_digest"],
            size=int(r["size"]),
            exit_code=int(r["exit_code"]),
            created_at=float(r["created_at"]),
            config_json=config_json,
            uploaded_by=uploaded_by,
        )

    # ---- organizations ---------------------------------------------------

    def create_org(
        self,
        *,
        name: str,
        owner_user_id: str,
        display_name: str = "",
        is_claimable: bool = False,
    ) -> OrgRow:
        org_id = name
        row = OrgRow(
            org_id=org_id,
            name=name,
            display_name=display_name or name,
            is_claimable=is_claimable,
            created_at=now(),
        )
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO organizations(
                        org_id, name, display_name, is_claimable, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row.org_id,
                        row.name,
                        row.display_name,
                        1 if row.is_claimable else 0,
                        row.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO org_memberships(org_id, user_id, role, created_at)
                    VALUES (?, ?, 'owner', ?)
                    """,
                    (row.org_id, owner_user_id, row.created_at),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("org already exists") from exc
        return row

    def get_org(self, org_id: str) -> OrgRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM organizations WHERE org_id=?",
                (org_id,),
            )
            r = cur.fetchone()
            return self._org_row(r) if r else None

    def list_orgs_for_user(self, user_id: str) -> list[tuple[OrgRow, str]]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT o.*, m.role AS membership_role
                FROM organizations o
                JOIN org_memberships m ON m.org_id = o.org_id
                WHERE m.user_id = ?
                ORDER BY o.name
                """,
                (user_id,),
            )
            out: list[tuple[OrgRow, str]] = []
            for r in cur.fetchall():
                out.append((self._org_row(r), str(r["membership_role"])))
            return out

    def claim_org(self, org_id: str, user_id: str) -> OrgRow:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM organizations WHERE org_id=?",
                (org_id,),
            )
            r = cur.fetchone()
            if r is None:
                raise LookupError("org not found")
            org = self._org_row(r)
            if not org.is_claimable:
                raise PermissionError("org not claimable")
            owners = conn.execute(
                "SELECT 1 FROM org_memberships WHERE org_id=? AND role='owner' LIMIT 1",
                (org_id,),
            ).fetchone()
            if owners is not None:
                raise PermissionError("org already claimed")
            conn.execute(
                """
                INSERT INTO org_memberships(org_id, user_id, role, created_at)
                VALUES (?, ?, 'owner', ?)
                """,
                (org_id, user_id, now()),
            )
            conn.execute(
                "UPDATE organizations SET is_claimable=0 WHERE org_id=?",
                (org_id,),
            )
            conn.commit()
        got = self.get_org(org_id)
        assert got is not None
        return got

    def add_member(self, org_id: str, user_id: str, *, role: str = "member") -> MembershipRow:
        if role not in {"owner", "member"}:
            raise ValueError("invalid role")
        ts = now()
        with self._connect() as conn:
            if self.get_org(org_id) is None:
                raise LookupError("org not found")
            try:
                conn.execute(
                    """
                    INSERT INTO org_memberships(org_id, user_id, role, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (org_id, user_id, role, ts),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("membership exists") from exc
        return MembershipRow(org_id=org_id, user_id=user_id, role=role, created_at=ts)

    def remove_member(self, org_id: str, user_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM org_memberships WHERE org_id=? AND user_id=?",
                (org_id, user_id),
            )
            if cur.rowcount == 0:
                raise LookupError("membership not found")
            conn.commit()

    def list_members(self, org_id: str) -> list[MembershipRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT org_id, user_id, role, created_at
                FROM org_memberships WHERE org_id=? ORDER BY role, user_id
                """,
                (org_id,),
            )
            return [
                MembershipRow(
                    org_id=str(r["org_id"]),
                    user_id=str(r["user_id"]),
                    role=str(r["role"]),
                    created_at=float(r["created_at"]),
                )
                for r in cur.fetchall()
            ]

    def membership(self, org_id: str, user_id: str) -> MembershipRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id, user_id, role, created_at FROM org_memberships "
                "WHERE org_id=? AND user_id=?",
                (org_id, user_id),
            )
            r = cur.fetchone()
            if r is None:
                return None
            return MembershipRow(
                org_id=str(r["org_id"]),
                user_id=str(r["user_id"]),
                role=str(r["role"]),
                created_at=float(r["created_at"]),
            )

    def user_org_ids(self, user_id: str) -> set[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id FROM org_memberships WHERE user_id=?",
                (user_id,),
            )
            return {str(r["org_id"]) for r in cur.fetchall()}

    # ---- result shares ---------------------------------------------------

    def add_result_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> ResultShareRow:
        if result_kind not in {"attempt", "suite"}:
            raise ValueError("invalid result_kind")
        if target_type not in {"org", "user"}:
            raise ValueError("invalid target_type")
        ts = now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO result_shares(
                        result_kind, result_id, target_type, target_id, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (result_kind, result_id, target_type, target_id, ts),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("share already exists") from exc
        return ResultShareRow(
            result_kind=result_kind,
            result_id=result_id,
            target_type=target_type,
            target_id=target_id,
            created_at=ts,
        )

    def remove_result_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM result_shares
                WHERE result_kind=? AND result_id=? AND target_type=? AND target_id=?
                """,
                (result_kind, result_id, target_type, target_id),
            )
            if cur.rowcount == 0:
                raise LookupError("share not found")
            conn.commit()

    def list_result_shares(self, *, result_kind: str, result_id: str) -> list[ResultShareRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM result_shares
                WHERE result_kind=? AND result_id=?
                ORDER BY target_type, target_id
                """,
                (result_kind, result_id),
            )
            return [
                ResultShareRow(
                    result_kind=str(r["result_kind"]),
                    result_id=str(r["result_id"]),
                    target_type=str(r["target_type"]),
                    target_id=str(r["target_id"]),
                    created_at=float(r["created_at"]),
                )
                for r in cur.fetchall()
            ]

    def result_shared_with_user(
        self,
        *,
        result_kind: str,
        result_id: str,
        user_id: str,
        user_orgs: set[str],
    ) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT 1 FROM result_shares
                WHERE result_kind=? AND result_id=? AND target_type='user' AND target_id=?
                LIMIT 1
                """,
                (result_kind, result_id, user_id),
            )
            if cur.fetchone() is not None:
                return True
            if not user_orgs:
                return False
            placeholders = ",".join("?" for _ in user_orgs)
            cur = conn.execute(
                f"""
                SELECT 1 FROM result_shares
                WHERE result_kind=? AND result_id=? AND target_type='org'
                  AND target_id IN ({placeholders})
                LIMIT 1
                """,
                (result_kind, result_id, *sorted(user_orgs)),
            )
            return cur.fetchone() is not None

    @staticmethod
    def _org_row(r: sqlite3.Row) -> OrgRow:
        return OrgRow(
            org_id=str(r["org_id"]),
            name=str(r["name"]),
            display_name=str(r["display_name"] or ""),
            is_claimable=bool(int(r["is_claimable"])),
            created_at=float(r["created_at"]),
        )


class PostgresMetadataStore:
    """Postgres release + attempt_results metadata."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg required for Postgres backend; install with: uv sync --extra registry"
            ) from exc
        self._psycopg = psycopg
        self.database_url = database_url
        self._init()

    def _connect(self):  # noqa: ANN202
        return self._psycopg.connect(self.database_url)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS releases (
                    database_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                    package_digest TEXT NOT NULL,
                    blob_digest TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    media_type TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (database_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_digest
                ON releases(database_id, package_digest)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attempt_results (
                    run_id TEXT PRIMARY KEY,
                    database_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    lock_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                    blob_digest TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suite_results (
                    suite_run_id TEXT PRIMARY KEY,
                    database_id TEXT NOT NULL,
                    database_version TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                    pass_rate DOUBLE PRECISION NOT NULL,
                    mean_score DOUBLE PRECISION NOT NULL,
                    metrics_json TEXT NOT NULL,
                    tasks_json TEXT NOT NULL,
                    agent_label TEXT NOT NULL DEFAULT '',
                    model_label TEXT NOT NULL DEFAULT '',
                    blob_digest TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    exit_code INTEGER NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL,
                    config_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            # Migrate pre-#42 DBs.
            conn.execute(
                """
                ALTER TABLE suite_results
                ADD COLUMN IF NOT EXISTS config_json TEXT NOT NULL DEFAULT '{}'
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    org_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    is_claimable BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS org_memberships (
                    org_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (org_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS result_shares (
                    result_kind TEXT NOT NULL,
                    result_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (result_kind, result_id, target_type, target_id)
                )
                """
            )
            conn.execute("ALTER TABLE releases ADD COLUMN IF NOT EXISTS org_id TEXT")
            conn.execute(
                "ALTER TABLE attempt_results "
                "ADD COLUMN IF NOT EXISTS uploaded_by TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE suite_results "
                "ADD COLUMN IF NOT EXISTS uploaded_by TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()

    def insert(self, row: ReleaseRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO releases(
                        database_id, version, visibility, package_digest,
                        blob_digest, size, media_type, created_at, org_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row.database_id,
                        row.version,
                        row.visibility,
                        row.package_digest,
                        row.blob_digest,
                        row.size,
                        row.media_type,
                        row.created_at,
                        row.org_id,
                    ),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("release already exists") from exc
                raise

    def get_by_version(self, database_id: str, version: str) -> ReleaseRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM releases WHERE database_id=%s AND version=%s",
                (database_id, version),
            )
            r = cur.fetchone()
            return self._release_from_cur(cur, r) if r else None

    def get_by_digest(self, database_id: str, package_digest: str) -> ReleaseRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM releases WHERE database_id=%s AND package_digest=%s",
                (database_id, package_digest),
            )
            r = cur.fetchone()
            return self._release_from_cur(cur, r) if r else None

    def list_releases(
        self,
        *,
        database_id_prefix: str | None = None,
        visibility: str | None = None,
        version: str | None = None,
        include_private: bool = False,
    ) -> list[ReleaseRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_private:
            clauses.append("visibility = 'public'")
        elif visibility in {"public", "private"}:
            clauses.append("visibility = %s")
            params.append(visibility)
        if database_id_prefix:
            clauses.append("database_id LIKE %s")
            params.append(f"{database_id_prefix}%")
        if version:
            clauses.append("version = %s")
            params.append(version)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM releases {where} ORDER BY database_id, version"
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
            return [self._release_from_cols(cols, r) for r in rows]

    def list_versions(self, database_id: str, *, include_private: bool = False) -> list[ReleaseRow]:
        clauses = ["database_id = %s"]
        params: list[Any] = [database_id]
        if not include_private:
            clauses.append("visibility = 'public'")
        where = " AND ".join(clauses)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM releases WHERE {where} ORDER BY version",
                params,
            )
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
            return [self._release_from_cols(cols, r) for r in rows]

    def insert_attempt(self, row: AttemptResultRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO attempt_results(
                        run_id, database_id, task_id, lock_digest, status,
                        visibility, blob_digest, size, created_at, uploaded_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row.run_id,
                        row.database_id,
                        row.task_id,
                        row.lock_digest,
                        row.status,
                        row.visibility,
                        row.blob_digest,
                        row.size,
                        row.created_at,
                        row.uploaded_by or "",
                    ),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("attempt result already exists") from exc
                raise

    def get_attempt(self, run_id: str) -> AttemptResultRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM attempt_results WHERE run_id=%s",
                (run_id,),
            )
            r = cur.fetchone()
            if r is None:
                return None
            cols = [d.name for d in cur.description] if cur.description else []
            return self._attempt_from_cols(cols, r)

    def list_attempts(
        self,
        *,
        database_id: str | None = None,
        include_private: bool = False,
    ) -> list[AttemptResultRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_private:
            clauses.append("visibility = 'public'")
        if database_id:
            clauses.append("database_id = %s")
            params.append(database_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM attempt_results {where} ORDER BY created_at DESC",
                params,
            )
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
            return [self._attempt_from_cols(cols, r) for r in rows]

    def insert_suite(self, row: SuiteResultRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO suite_results(
                        suite_run_id, database_id, database_version, visibility,
                        pass_rate, mean_score, metrics_json, tasks_json,
                        agent_label, model_label, blob_digest, size,
                        exit_code, created_at, config_json, uploaded_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row.suite_run_id,
                        row.database_id,
                        row.database_version,
                        row.visibility,
                        row.pass_rate,
                        row.mean_score,
                        row.metrics_json,
                        row.tasks_json,
                        row.agent_label,
                        row.model_label,
                        row.blob_digest,
                        row.size,
                        row.exit_code,
                        row.created_at,
                        row.config_json or "{}",
                        row.uploaded_by or "",
                    ),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("suite result already exists") from exc
                raise

    def get_suite(self, suite_run_id: str) -> SuiteResultRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM suite_results WHERE suite_run_id=%s",
                (suite_run_id,),
            )
            r = cur.fetchone()
            if r is None:
                return None
            cols = [d.name for d in cur.description] if cur.description else []
            return self._suite_from_cols(cols, r)

    def list_suites(
        self,
        *,
        database_id: str | None = None,
        include_private: bool = False,
    ) -> list[SuiteResultRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_private:
            clauses.append("visibility = 'public'")
        if database_id:
            clauses.append("database_id = %s")
            params.append(database_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM suite_results {where} ORDER BY created_at DESC",
                params,
            )
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
            return [self._suite_from_cols(cols, r) for r in rows]

    @staticmethod
    def _release_from_cur(cur: Any, r: Any) -> ReleaseRow:
        cols = [d.name for d in cur.description]
        return PostgresMetadataStore._release_from_cols(cols, r)

    @staticmethod
    def _release_from_cols(cols: list[str], r: Any) -> ReleaseRow:
        d = dict(zip(cols, r, strict=True))
        org_raw = d.get("org_id")
        return ReleaseRow(
            database_id=str(d["database_id"]),
            version=str(d["version"]),
            visibility=str(d["visibility"]),
            package_digest=str(d["package_digest"]),
            blob_digest=str(d["blob_digest"]),
            size=int(d["size"]),
            media_type=str(d["media_type"]),
            created_at=float(d["created_at"]),
            org_id=str(org_raw) if org_raw else None,
        )

    @staticmethod
    def _attempt_from_cols(cols: list[str], r: Any) -> AttemptResultRow:
        d = dict(zip(cols, r, strict=True))
        return AttemptResultRow(
            run_id=str(d["run_id"]),
            database_id=str(d["database_id"]),
            task_id=str(d["task_id"]),
            lock_digest=str(d["lock_digest"]),
            status=str(d["status"]),
            visibility=str(d["visibility"]),
            blob_digest=str(d["blob_digest"]),
            size=int(d["size"]),
            created_at=float(d["created_at"]),
            uploaded_by=str(d.get("uploaded_by") or ""),
        )

    @staticmethod
    def _suite_from_cols(cols: list[str], r: Any) -> SuiteResultRow:
        d = dict(zip(cols, r, strict=True))
        return SuiteResultRow(
            suite_run_id=str(d["suite_run_id"]),
            database_id=str(d["database_id"]),
            database_version=str(d["database_version"]),
            visibility=str(d["visibility"]),
            pass_rate=float(d["pass_rate"]),
            mean_score=float(d["mean_score"]),
            metrics_json=str(d["metrics_json"]),
            tasks_json=str(d["tasks_json"]),
            agent_label=str(d.get("agent_label") or ""),
            model_label=str(d.get("model_label") or ""),
            blob_digest=str(d["blob_digest"]),
            size=int(d["size"]),
            exit_code=int(d["exit_code"]),
            created_at=float(d["created_at"]),
            config_json=str(d.get("config_json") or "{}"),
            uploaded_by=str(d.get("uploaded_by") or ""),
        )

    # Delegate org/share to same SQL shape as SQLite (psycopg %s).
    def create_org(
        self,
        *,
        name: str,
        owner_user_id: str,
        display_name: str = "",
        is_claimable: bool = False,
    ) -> OrgRow:
        org_id = name
        row = OrgRow(
            org_id=org_id,
            name=name,
            display_name=display_name or name,
            is_claimable=is_claimable,
            created_at=now(),
        )
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO organizations(
                        org_id, name, display_name, is_claimable, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        row.org_id,
                        row.name,
                        row.display_name,
                        row.is_claimable,
                        row.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO org_memberships(org_id, user_id, role, created_at)
                    VALUES (%s, %s, 'owner', %s)
                    """,
                    (row.org_id, owner_user_id, row.created_at),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("org already exists") from exc
                raise
        return row

    def get_org(self, org_id: str) -> OrgRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id, name, display_name, is_claimable, created_at "
                "FROM organizations WHERE org_id=%s",
                (org_id,),
            )
            r = cur.fetchone()
            if r is None:
                return None
            return OrgRow(
                org_id=str(r[0]),
                name=str(r[1]),
                display_name=str(r[2] or ""),
                is_claimable=bool(r[3]),
                created_at=float(r[4]),
            )

    def list_orgs_for_user(self, user_id: str) -> list[tuple[OrgRow, str]]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT o.org_id, o.name, o.display_name, o.is_claimable, o.created_at, m.role
                FROM organizations o
                JOIN org_memberships m ON m.org_id = o.org_id
                WHERE m.user_id = %s
                ORDER BY o.name
                """,
                (user_id,),
            )
            out: list[tuple[OrgRow, str]] = []
            for r in cur.fetchall():
                out.append(
                    (
                        OrgRow(
                            org_id=str(r[0]),
                            name=str(r[1]),
                            display_name=str(r[2] or ""),
                            is_claimable=bool(r[3]),
                            created_at=float(r[4]),
                        ),
                        str(r[5]),
                    )
                )
            return out

    def claim_org(self, org_id: str, user_id: str) -> OrgRow:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id, name, display_name, is_claimable, created_at "
                "FROM organizations WHERE org_id=%s",
                (org_id,),
            )
            r = cur.fetchone()
            if r is None:
                raise LookupError("org not found")
            if not bool(r[3]):
                raise PermissionError("org not claimable")
            owners = conn.execute(
                "SELECT 1 FROM org_memberships WHERE org_id=%s AND role='owner' LIMIT 1",
                (org_id,),
            ).fetchone()
            if owners is not None:
                raise PermissionError("org already claimed")
            conn.execute(
                """
                INSERT INTO org_memberships(org_id, user_id, role, created_at)
                VALUES (%s, %s, 'owner', %s)
                """,
                (org_id, user_id, now()),
            )
            conn.execute(
                "UPDATE organizations SET is_claimable=FALSE WHERE org_id=%s",
                (org_id,),
            )
            conn.commit()
        got = self.get_org(org_id)
        assert got is not None
        return got

    def add_member(self, org_id: str, user_id: str, *, role: str = "member") -> MembershipRow:
        if role not in {"owner", "member"}:
            raise ValueError("invalid role")
        ts = now()
        if self.get_org(org_id) is None:
            raise LookupError("org not found")
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO org_memberships(org_id, user_id, role, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (org_id, user_id, role, ts),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("membership exists") from exc
                raise
        return MembershipRow(org_id=org_id, user_id=user_id, role=role, created_at=ts)

    def remove_member(self, org_id: str, user_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM org_memberships WHERE org_id=%s AND user_id=%s",
                (org_id, user_id),
            )
            if cur.rowcount == 0:
                raise LookupError("membership not found")
            conn.commit()

    def list_members(self, org_id: str) -> list[MembershipRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT org_id, user_id, role, created_at
                FROM org_memberships WHERE org_id=%s ORDER BY role, user_id
                """,
                (org_id,),
            )
            return [
                MembershipRow(
                    org_id=str(r[0]),
                    user_id=str(r[1]),
                    role=str(r[2]),
                    created_at=float(r[3]),
                )
                for r in cur.fetchall()
            ]

    def membership(self, org_id: str, user_id: str) -> MembershipRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id, user_id, role, created_at FROM org_memberships "
                "WHERE org_id=%s AND user_id=%s",
                (org_id, user_id),
            )
            r = cur.fetchone()
            if r is None:
                return None
            return MembershipRow(
                org_id=str(r[0]),
                user_id=str(r[1]),
                role=str(r[2]),
                created_at=float(r[3]),
            )

    def user_org_ids(self, user_id: str) -> set[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT org_id FROM org_memberships WHERE user_id=%s",
                (user_id,),
            )
            return {str(r[0]) for r in cur.fetchall()}

    def add_result_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> ResultShareRow:
        if result_kind not in {"attempt", "suite"}:
            raise ValueError("invalid result_kind")
        if target_type not in {"org", "user"}:
            raise ValueError("invalid target_type")
        ts = now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO result_shares(
                        result_kind, result_id, target_type, target_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (result_kind, result_id, target_type, target_id, ts),
                )
                conn.commit()
            except Exception as exc:
                if type(exc).__name__ == "UniqueViolation" or "unique" in str(exc).lower():
                    raise ValueError("share already exists") from exc
                raise
        return ResultShareRow(
            result_kind=result_kind,
            result_id=result_id,
            target_type=target_type,
            target_id=target_id,
            created_at=ts,
        )

    def remove_result_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM result_shares
                WHERE result_kind=%s AND result_id=%s AND target_type=%s AND target_id=%s
                """,
                (result_kind, result_id, target_type, target_id),
            )
            if cur.rowcount == 0:
                raise LookupError("share not found")
            conn.commit()

    def list_result_shares(self, *, result_kind: str, result_id: str) -> list[ResultShareRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT result_kind, result_id, target_type, target_id, created_at
                FROM result_shares
                WHERE result_kind=%s AND result_id=%s
                ORDER BY target_type, target_id
                """,
                (result_kind, result_id),
            )
            return [
                ResultShareRow(
                    result_kind=str(r[0]),
                    result_id=str(r[1]),
                    target_type=str(r[2]),
                    target_id=str(r[3]),
                    created_at=float(r[4]),
                )
                for r in cur.fetchall()
            ]

    def result_shared_with_user(
        self,
        *,
        result_kind: str,
        result_id: str,
        user_id: str,
        user_orgs: set[str],
    ) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT 1 FROM result_shares
                WHERE result_kind=%s AND result_id=%s AND target_type='user' AND target_id=%s
                LIMIT 1
                """,
                (result_kind, result_id, user_id),
            )
            if cur.fetchone() is not None:
                return True
            if not user_orgs:
                return False
            cur = conn.execute(
                """
                SELECT 1 FROM result_shares
                WHERE result_kind=%s AND result_id=%s AND target_type='org'
                  AND target_id = ANY(%s)
                LIMIT 1
                """,
                (result_kind, result_id, list(user_orgs)),
            )
            return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def release_to_dict(row: ReleaseRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "database_id": row.database_id,
        "version": row.version,
        "visibility": row.visibility,
        "package_digest": row.package_digest,
        "blob_digest": row.blob_digest,
        "size": row.size,
        "media_type": row.media_type,
        "created_at": row.created_at,
    }
    if row.org_id:
        out["org_id"] = row.org_id
    return out


def attempt_to_dict(row: AttemptResultRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_id": row.run_id,
        "database_id": row.database_id,
        "task_id": row.task_id,
        "lock_digest": row.lock_digest,
        "status": row.status,
        "visibility": row.visibility,
        "blob_digest": row.blob_digest,
        "size": row.size,
        "created_at": row.created_at,
    }
    if row.uploaded_by:
        out["uploaded_by"] = row.uploaded_by
    return out


def org_to_dict(row: OrgRow) -> dict[str, Any]:
    return {
        "org_id": row.org_id,
        "name": row.name,
        "display_name": row.display_name,
        "is_claimable": row.is_claimable,
        "created_at": row.created_at,
    }


def membership_to_dict(row: MembershipRow) -> dict[str, Any]:
    return {
        "org_id": row.org_id,
        "user_id": row.user_id,
        "role": row.role,
        "created_at": row.created_at,
    }


def share_to_dict(row: ResultShareRow) -> dict[str, Any]:
    return {
        "result_kind": row.result_kind,
        "result_id": row.result_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "created_at": row.created_at,
    }


def suite_to_dict(row: SuiteResultRow) -> dict[str, Any]:
    """Serialize suite result; never invent a suite-level PASS field."""
    try:
        metrics = json.loads(row.metrics_json)
    except (json.JSONDecodeError, TypeError):
        metrics = {}
    try:
        task_refs = json.loads(row.tasks_json)
    except (json.JSONDecodeError, TypeError):
        task_refs = []
    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(task_refs, list):
        task_refs = []
    out: dict[str, Any] = {
        "suite_run_id": row.suite_run_id,
        "database_id": row.database_id,
        "database_version": row.database_version,
        "visibility": row.visibility,
        "pass_rate": row.pass_rate,
        "mean_score": row.mean_score,
        "metrics": metrics,
        "task_refs": task_refs,
        "agent_label": row.agent_label,
        "model_label": row.model_label,
        "blob_digest": row.blob_digest,
        "size": row.size,
        "exit_code": row.exit_code,
        "created_at": row.created_at,
        # Explicit: no suite PASS authority
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
    if row.uploaded_by:
        out["uploaded_by"] = row.uploaded_by
    # #42 config fingerprint projection (absent on legacy rows)
    try:
        cfg = json.loads(row.config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        cfg = {}
    if isinstance(cfg, dict):
        if cfg.get("config_fingerprint"):
            out["config_fingerprint"] = cfg["config_fingerprint"]
        if "config_homogeneous" in cfg:
            out["config_homogeneous"] = bool(cfg["config_homogeneous"])
        actors = cfg.get("actors_summary")
        if isinstance(actors, list):
            out["actors_summary"] = actors
    return out


def now() -> float:
    return time.time()
