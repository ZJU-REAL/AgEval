"""PostgreSQL Environment Adapter (v0.10 minimal real resource).

Resource-type named adapter — no Benchmark branches.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PostgresEnvironment:
    """Attempt-local Postgres via Docker (requires daemon)."""

    container_name: str
    image: str = "postgres:16-alpine"
    user: str = "bora"
    password: str = "bora-attempt"
    database: str = "bora"
    port: int = 0
    ready: bool = False
    actions: int = 0
    action_limit: int = 10
    allowed_actions: frozenset[str] = field(default_factory=lambda: frozenset({"query", "execute"}))

    def start(self, *, timeout: float = 60.0) -> None:
        name = self.container_name
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            f"POSTGRES_USER={self.user}",
            "-e",
            f"POSTGRES_PASSWORD={self.password}",
            "-e",
            f"POSTGRES_DB={self.database}",
            "-p",
            "0:5432",
            self.image,
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"postgres start failed: {proc.stderr}")
        # Wait for readiness
        deadline = time.time() + timeout
        while time.time() < deadline:
            chk = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", self.user, "-d", self.database],
                check=False,
                capture_output=True,
                text=True,
            )
            if chk.returncode == 0:
                self.ready = True
                return
            time.sleep(0.5)
        self.stop()
        raise TimeoutError("postgres health timeout")

    def action(self, action_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError("environment not ready")
        if action_id not in self.allowed_actions:
            return {
                "ok": False,
                "error": "environment_action_denied",
                "action": action_id,
            }
        if self.actions >= self.action_limit:
            return {
                "ok": False,
                "error": "environment_action_limit_exceeded",
                "action": action_id,
            }
        self.actions += 1
        sql = str((args or {}).get("sql") or "SELECT 1")
        # Only allow simple statements for MVP safety
        lowered = sql.lower()
        if "drop " in lowered or "alter " in lowered or "copy " in lowered:
            return {"ok": False, "error": "environment_action_denied", "action": action_id}
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={self.password}",
                self.container_name,
                "psql",
                "-U",
                self.user,
                "-d",
                self.database,
                "-t",
                "-A",
                "-c",
                sql,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "action": action_id,
            "count": self.actions,
        }

    def stop(self) -> None:
        # -v drops anonymous Postgres data volumes; --rm does not on force-rm.
        subprocess.run(
            ["docker", "rm", "-fv", self.container_name],
            check=False,
            capture_output=True,
        )
        self.ready = False


def new_postgres_environment() -> PostgresEnvironment:
    return PostgresEnvironment(container_name=f"bora-pg-{uuid.uuid4().hex[:10]}")
