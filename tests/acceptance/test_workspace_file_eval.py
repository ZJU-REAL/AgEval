"""Type B terminal workspace package acceptance (offline fail-closed)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _bora(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )


def test_lock_terminal_package() -> None:
    r = _bora("lock", str(REPO / "examples" / "workspace-file-eval"), "--task", "workspace-file-eval")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["task_id"] == "workspace-file-eval"


def test_offline_not_pass() -> None:
    r = _bora("run", str(REPO / "examples" / "workspace-file-eval"), "--task", "workspace-file-eval")
    assert r.returncode != 0, r.stdout
    data = json.loads(r.stdout)
    assert data["status"] != "PASS"
