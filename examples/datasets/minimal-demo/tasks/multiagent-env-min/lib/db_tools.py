"""PostgreSQL query tool bound to Attempt-local environment handoff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ageval_sdk import Tool, ToolSet


def load_env_meta(package_dir: Path, workspace_root: Path) -> dict[str, Any]:
    for path in (
        package_dir / ".ageval_env_result.json",
        workspace_root / ".ageval_env_result.json",
        Path.cwd() / ".ageval_env_result.json",
    ):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("ok"):
                raise RuntimeError(data.get("error") or "environment_failed")
            return data
    raise FileNotFoundError("environment_result_missing")


def build_db_toolset(env: dict[str, Any]) -> ToolSet:
    container = str(env.get("container") or "")
    user = str(env.get("user") or "ageval")
    database = str(env.get("database") or "ageval")
    password = str(env.get("password") or "ageval-attempt")
    host = str(env.get("host") or "")

    def db_query(args: dict[str, Any]) -> dict[str, Any]:
        sql = str(args.get("sql") or "").strip()
        if not sql:
            return {"ok": False, "error": "empty_sql"}
        lowered = sql.lower()
        if not lowered.startswith("select"):
            return {"ok": False, "error": "read_only_select_only"}
        if any(tok in lowered for tok in ("insert ", "update ", "delete ", "drop ", "alter ")):
            return {"ok": False, "error": "mutation_denied"}
        if not container:
            return {"ok": False, "error": "missing_container"}
        host_flag = ["-h", host] if host else []
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={password}",
                container,
                "psql",
                *host_flag,
                "-U",
                user,
                "-d",
                database,
                "-t",
                "-A",
                "-F",
                "|",
                "-c",
                sql,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip()[-500:],
            "sql": sql,
        }

    ts = ToolSet(allowlist={"db_query"})
    ts.add(Tool(name="db_query", fn=db_query, schema={"required": ["sql"]}))
    return ts
