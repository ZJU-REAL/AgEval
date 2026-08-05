"""Acceptance: lock package for L1 SDK single-actor path (offline fail-closed)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "examples" / "l1"


@pytest.mark.skipif(not PKG.is_dir(), reason="example package missing")
def test_lock_sdk_session_single_actor() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "lock", str(PKG), "--task", "sdk-session-single-actor"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


@pytest.mark.skipif(not PKG.is_dir(), reason="example package missing")
def test_offline_sdk_l1_fail_closed_no_host() -> None:
    """Offline: fail closed without inventing PASS or host fallback."""
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(PKG),
            "--task",
            "sdk-session-single-actor",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=180,
    )
    # Offline agent must not PASS.
    assert proc.returncode != 0
