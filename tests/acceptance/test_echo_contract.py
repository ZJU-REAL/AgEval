"""Thin agent structured-output acceptance (formerly echo-contract / agent-eval).

Retargeted to ``examples/core`` — lock + offline fail-closed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "examples" / "core"


def _bora(*args: str, offline: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1" if offline else "0"
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=180,
    )


def test_sdk_agent_session_lock() -> None:
    result = _bora("lock", str(PKG), "--task", "sdk-agent-session")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["task_id"] == "sdk-agent-session"
    assert "digest" in data


def test_sdk_agent_session_offline_fail_closed() -> None:
    result = _bora("run", str(PKG), "--task", "sdk-agent-session")
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
