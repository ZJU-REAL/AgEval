"""Deterministic ToolSet public packages via production CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run(package: str, task: str) -> dict:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "core"),
            "--task",
            task,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def test_sdk_tool_guard_success() -> None:
    data = _run("sdk-tool-guard", "sdk-tool-guard")
    assert data["status"] == "PASS"
    assert data["score"] == 1.0
    assert data.get("assurance") == "l0"


def test_sdk_tool_guard_denied() -> None:
    data = _run("sdk-tool-guard-denied", "sdk-tool-guard-denied")
    assert data["status"] == "PASS"
    assert data["score"] == 1.0
