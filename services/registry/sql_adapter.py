"""Thin SQLite / Postgres connection adapters.

SQL text (including DDL) lives in ``queries``. These types only connect,
translate placeholders, and map rows to ``Mapping``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.registry.dialect import pg_sql


class _MappedCursor:
    """Wrap a DB-API cursor so fetchone/fetchall return mappings."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur
        desc = getattr(cur, "description", None)
        self._cols = [d[0] for d in desc] if desc else []
        raw_rc = getattr(cur, "rowcount", -1)
        self.rowcount = -1 if raw_rc is None else int(raw_rc)
        self.lastrowid = getattr(cur, "lastrowid", None)

    def fetchone(self) -> Mapping[str, Any] | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, Mapping):
            return row
        if hasattr(row, "keys"):
            return {str(k): row[k] for k in list(row.keys())}
        return dict(zip(self._cols, row, strict=False))

    def fetchall(self) -> list[Mapping[str, Any]]:
        rows = self._cur.fetchall()
        out: list[Mapping[str, Any]] = []
        for row in rows:
            if isinstance(row, Mapping):
                out.append(row)
            elif hasattr(row, "keys"):
                out.append({str(k): row[k] for k in list(row.keys())})
            else:
                out.append(dict(zip(self._cols, row, strict=False)))
        return out


class SqliteAdapter:
    """SQLite connect / execute / row-map."""

    name = "sqlite"
    integrity_error = sqlite3.IntegrityError

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, conn: Any, sql: str, params: Sequence[Any] | Any = ()) -> _MappedCursor:
        return _MappedCursor(conn.execute(sql, params))

    def table_columns(self, conn: Any, table: str) -> set[str]:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return {str(r[1]) for r in cur.fetchall()}

    def add_column(self, conn: Any, table: str, column: str, decl: str) -> None:
        if column in self.table_columns(conn, table):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


class PostgresAdapter:
    """Postgres connect / placeholder translation / row-map."""

    name = "postgres"

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg required for Postgres backend; install with: uv sync --extra registry"
            ) from exc
        self._psycopg = psycopg
        self.database_url = database_url
        self.integrity_error = getattr(psycopg, "IntegrityError", Exception)

    def connect(self) -> Any:
        return self._psycopg.connect(self.database_url)

    def execute(self, conn: Any, sql: str, params: Sequence[Any] | Any = ()) -> _MappedCursor:
        return _MappedCursor(conn.execute(pg_sql(sql), params))

    def table_columns(self, conn: Any, table: str) -> set[str]:
        cur = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {str(r[0]) for r in cur.fetchall()}

    def add_column(self, conn: Any, table: str, column: str, decl: str) -> None:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {decl}")
