"""Public entrypoint: bora executors lists ACP + openai-http."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run_bora(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    cmd = [sys.executable, "-m", "bora.cli.main", *args]
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )


def test_executors_lists_supported_and_host_probe() -> None:
    result = _run_bora("executors")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert set(data) >= {
        "supported",
        "host_ready",
        "missing_binary",
        "executors",
        "acp_entries",
    }
    assert "Official/acp" in data["supported"]
    assert "Official/openai-http" in data["supported"]
    for gone in ("codex", "pi", "opencode", "claude-code"):
        assert gone not in data["supported"]

    by_kind = {r["kind"]: r for r in data["executors"]}
    http = by_kind["Official/openai-http"]
    assert http["execution_mode"] == "api-client"
    assert http["host_ready"] is True
    assert "sk-" not in result.stdout.lower()

    entry_ids = {r["entry_id"] for r in data["acp_entries"]}
    assert {"codex", "pi", "opencode", "claude-code", "grok-build"} <= entry_ids


def test_executors_verbose_adds_detail() -> None:
    result = _run_bora("executors", "-v")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    by_kind = {r["kind"]: r for r in data["executors"]}
    assert by_kind["Official/acp"].get("tools") is not None or data.get("acp_entries")
    acp_rows = {r["entry_id"]: r for r in data["acp_entries"]}
    assert "credential_env_names" in acp_rows["opencode"]
