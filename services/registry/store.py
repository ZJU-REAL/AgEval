"""Registry metadata, tokens, results, and blob storage.

Unit tests: SQLite + Memory blob.
Compose / production: Postgres + S3-compatible (RustFS).

Raw API tokens are never persisted — only sha256 digests.
Visibility is only ``public`` | ``private`` (no org in this MVP).
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


class TokenStore:
    """In-memory tokens (tests). Prefer SqliteTokenStore / PostgresTokenStore."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, frozenset[str]] = {}

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
        del github_user
        with self._lock:
            self._tokens[self.hash_token(raw_token)] = frozenset(scopes)

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        if not raw_token:
            return frozenset()
        with self._lock:
            return self._tokens.get(self.hash_token(raw_token), frozenset())


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

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        if not raw_token:
            return frozenset()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT scopes, revoked_at FROM api_tokens WHERE token_hash=?",
                (self.hash_token(raw_token),),
            )
            row = cur.fetchone()
            if row is None or row["revoked_at"] is not None:
                return frozenset()
            try:
                data = json.loads(row["scopes"])
            except json.JSONDecodeError:
                return frozenset()
            return frozenset(str(s) for s in data)


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

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        if not raw_token:
            return frozenset()
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT scopes FROM api_tokens
                WHERE token_hash = %s AND revoked_at IS NULL
                """,
                (self.hash_token(raw_token),),
            )
            row = cur.fetchone()
            if row is None:
                return frozenset()
            scopes = row[0]
            if isinstance(scopes, list):
                return frozenset(str(s) for s in scopes)
            if isinstance(scopes, str):
                return frozenset(str(s) for s in json.loads(scopes))
            return frozenset()


# ---------------------------------------------------------------------------
# Metadata (packages + attempt results)
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
            conn.commit()

    def insert(self, row: ReleaseRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO releases(
                        database_id, version, visibility, package_digest,
                        blob_digest, size, media_type, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                        visibility, blob_digest, size, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    @staticmethod
    def _release_row(r: sqlite3.Row) -> ReleaseRow:
        return ReleaseRow(
            database_id=r["database_id"],
            version=r["version"],
            visibility=r["visibility"],
            package_digest=r["package_digest"],
            blob_digest=r["blob_digest"],
            size=int(r["size"]),
            media_type=r["media_type"],
            created_at=float(r["created_at"]),
        )

    @staticmethod
    def _attempt_row(r: sqlite3.Row) -> AttemptResultRow:
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
            conn.commit()

    def insert(self, row: ReleaseRow) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO releases(
                        database_id, version, visibility, package_digest,
                        blob_digest, size, media_type, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                        visibility, blob_digest, size, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    @staticmethod
    def _release_from_cur(cur: Any, r: Any) -> ReleaseRow:
        cols = [d.name for d in cur.description]
        return PostgresMetadataStore._release_from_cols(cols, r)

    @staticmethod
    def _release_from_cols(cols: list[str], r: Any) -> ReleaseRow:
        d = dict(zip(cols, r, strict=True))
        return ReleaseRow(
            database_id=str(d["database_id"]),
            version=str(d["version"]),
            visibility=str(d["visibility"]),
            package_digest=str(d["package_digest"]),
            blob_digest=str(d["blob_digest"]),
            size=int(d["size"]),
            media_type=str(d["media_type"]),
            created_at=float(d["created_at"]),
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
        )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def release_to_dict(row: ReleaseRow) -> dict[str, Any]:
    return {
        "database_id": row.database_id,
        "version": row.version,
        "visibility": row.visibility,
        "package_digest": row.package_digest,
        "blob_digest": row.blob_digest,
        "size": row.size,
        "media_type": row.media_type,
        "created_at": row.created_at,
    }


def attempt_to_dict(row: AttemptResultRow) -> dict[str, Any]:
    return {
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


def now() -> float:
    return time.time()
