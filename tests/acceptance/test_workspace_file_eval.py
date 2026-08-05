"""Workspace file-eval acceptance (formerly workspace-file-eval; package removed).

Retargeted to ``examples/journeys`` — workspace aggregates path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "examples" / "journeys"


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
    r = _bora("lock", str(PKG), "--task", "terminal-jsonl-agg")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["task_id"] == "terminal-jsonl-agg"


def test_offline_not_pass() -> None:
    r = _bora("run", str(PKG), "--task", "terminal-jsonl-agg")
    assert r.returncode != 0, r.stdout
    data = json.loads(r.stdout)
    assert data["status"] != "PASS"
