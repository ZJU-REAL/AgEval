"""Acceptance: multi-agent packages lock + offline fail-closed (Spec 18 Phase 4)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "examples" / "l1"
PER_GROUP = ROOT / "examples" / "l1"


@pytest.mark.parametrize(
    "pkg,task",
    [
        (SHARED, "multi-agent-shared-container"),
        (PER_GROUP, "multi-agent-container-per-group"),
    ],
)
def test_lock_multi_agent_packages(pkg: Path, task: str) -> None:
    assert pkg.is_dir()
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "lock", str(pkg), "--task", task],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


@pytest.mark.parametrize(
    "pkg,task",
    [
        (SHARED, "multi-agent-shared-container"),
        (PER_GROUP, "multi-agent-container-per-group"),
    ],
)
def test_offline_multi_agent_fail_closed(pkg: Path, task: str) -> None:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "run", str(pkg), "--task", task],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=240,
    )
    assert proc.returncode != 0
