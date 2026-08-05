"""Spec 07 public L1 CLI journeys (Docker required).

Isolation contracts (hidden gold / projection / writer-stop) live under
``tests/provider_l1/`` — not Application task_id probe branches.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"], check=False, capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def test_terminal_jsonl_l1_solution_seed() -> None:
    e = os.environ.copy()
    e["BORA_L1_USE_SOLUTION"] = "1"
    e["BORA_OFFLINE_AGENT"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "journeys" / "terminal-jsonl-agg"),
            "--task",
            "terminal-jsonl-agg",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=e,
        timeout=300,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    assert data.get("l1", {}).get("full_l1") is True
