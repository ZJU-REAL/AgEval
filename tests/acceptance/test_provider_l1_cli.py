"""Spec 07 public L1 CLI journeys (Docker required)."""

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


def _run(package: str, task: str, *, env: dict | None = None) -> dict:
    e = os.environ.copy()
    if env:
        e.update(env)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / package),
            "--task",
            task,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=e,
        timeout=300,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def test_hidden_material_denied() -> None:
    data = _run("provider-l1-denied", "hidden-material-denied")
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    # Gold not visible; harness failed closed (l1 evidence on disk).
    assert data.get("harness_kind") == "failed"


def test_projection_denied() -> None:
    data = _run("provider-l1-projection-denied", "projection-denied")
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"


def test_residual_writer() -> None:
    data = _run("provider-l1-residual-writer", "residual-writer")
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    assert data.get("l1", {}).get("writer_stop_confirmed") is True
    assert data.get("l1", {}).get("evaluator_started") is False


def test_terminal_jsonl_l1_solution_seed() -> None:
    data = _run(
        "terminal-jsonl-agg",
        "terminal-jsonl-agg",
        env={"BORA_L1_USE_SOLUTION": "1", "BORA_OFFLINE_AGENT": "1"},
    )
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    assert data.get("l1", {}).get("full_l1") is True
