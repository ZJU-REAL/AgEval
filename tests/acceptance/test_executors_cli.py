"""Public entrypoint: bora executors lists supported kinds + host binary probe."""

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

    assert set(data) >= {"supported", "host_ready", "missing_binary", "executors"}
    assert "required_v014" not in data
    assert "residual" not in data

    for required in ("codex", "pi", "opencode", "openai-http", "claude-code"):
        assert required in data["supported"]

    by_kind = {r["kind"]: r for r in data["executors"]}
    for kind in ("codex", "pi", "opencode", "claude-code"):
        row = by_kind[kind]
        assert row["execution_mode"] == "cli-process"
        assert isinstance(row["binary_on_path"], bool)
        assert row["host_ready"] is row["binary_on_path"]
        # Default output stays lean: credential names only with -v.
        assert "credential_env_names" not in row

    http = by_kind["openai-http"]
    assert http["execution_mode"] == "api-client"
    assert http["binary_on_path"] is None
    assert http["host_ready"] is True
    assert "sk-" not in result.stdout.lower()


def test_executors_verbose_adds_detail() -> None:
    result = _run_bora("executors", "-v")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    by_kind = {r["kind"]: r for r in data["executors"]}
    assert by_kind["codex"].get("tools") is not None
    assert isinstance(by_kind["claude-code"].get("credential_env_names"), list)
