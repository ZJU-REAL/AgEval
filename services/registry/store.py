"""Registry metadata + blob storage.

v1 default for in-process / tests: SQLite metadata + filesystem blob putIfAbsent.
Postgres + S3-compatible (RustFS) are the production compose targets; the blob
protocol is the same ``put_if_absent`` / ``get`` surface.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


class TokenStore:
    """API tokens stored as sha256 digests; raw token never persisted."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # digest -> set of scopes
        self._tokens: dict[str, frozenset[str]] = {}

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add(self, raw_token: str, scopes: set[str] | frozenset[str]) -> None:
        with self._lock:
            self._tokens[self.hash_token(raw_token)] = frozenset(scopes)

    def scopes_for(self, raw_token: str | None) -> frozenset[str]:
        if not raw_token:
            return frozenset()
        with self._lock:
            return self._tokens.get(self.hash_token(raw_token), frozenset())


class BlobStore:
    def put_if_absent(self, blob_digest: str, data: bytes) -> None:
        raise NotImplementedError

    def get(self, blob_digest: str) -> bytes | None:
        raise NotImplementedError


class FilesystemBlobStore(BlobStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, blob_digest: str) -> Path:
        key = blob_digest.replace(":", "_")
        return self.root / key

    def put_if_absent(self, blob_digest: str, data: bytes) -> None:
        path = self._path(blob_digest)
        if path.exists():
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, blob_digest: str) -> bytes | None:
        path = self._path(blob_digest)
        if not path.is_file():
            return None
        return path.read_bytes()


class MemoryBlobStore(BlobStore):
    """Unit-test only blob backend (Spec 21 allows memory for single tests)."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put_if_absent(self, blob_digest: str, data: bytes) -> None:
        with self._lock:
            self._data.setdefault(blob_digest, data)

    def get(self, blob_digest: str) -> bytes | None:
        with self._lock:
            return self._data.get(blob_digest)


class MetadataStore:
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
            return self._row(r) if r else None

    def get_by_digest(self, database_id: str, package_digest: str) -> ReleaseRow | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM releases WHERE database_id=? AND package_digest=?",
                (database_id, package_digest),
            )
            r = cur.fetchone()
            return self._row(r) if r else None

    @staticmethod
    def _row(r: sqlite3.Row) -> ReleaseRow:
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


def now() -> float:
    return time.time()
