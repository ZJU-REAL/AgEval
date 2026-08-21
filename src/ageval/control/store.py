"""Durable control store sketch (v0.12) — SQLite Run control records.

Only used when durable control is explicitly enabled; foreground path remains default.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ControlStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def put(self, run_id: str, *, status: str, owner: str, payload: Mapping[str, Any]) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT version FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            version = int(row[0]) + 1 if row else 1
            conn.execute(
                """
                INSERT INTO runs(run_id, version, status, owner, payload, updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                  version=excluded.version,
                  status=excluded.status,
                  owner=excluded.owner,
                  payload=excluded.payload,
                  updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    version,
                    status,
                    owner,
                    json.dumps(dict(payload), sort_keys=True),
                    time.time(),
                ),
            )
            return version

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id, version, status, owner, payload, updated_at "
                "FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "version": row[1],
            "status": row[2],
            "owner": row[3],
            "payload": json.loads(row[4]),
            "updated_at": row[5],
        }
