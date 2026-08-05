"""L1 terminal-class journey: harness isolation + clean evaluator (solution seed)."""

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
        p = subprocess.run(["docker", "info"], check=False, capture_output=True, timeout=10)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")
def test_terminal_jsonl_agg_l1_solution_seed_pass() -> None:
    env = os.environ.copy()
    env["BORA_L1_USE_SOLUTION"] = "1"
    env["BORA_OFFLINE_AGENT"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "journeys"),
            "--task",
            "terminal-jsonl-agg",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=180,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    assert data.get("score") == 1.0
