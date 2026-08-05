"""Spec 06 named acceptance path: session authority negatives + offline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_offline_session_not_pass() -> None:
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
            "sdk-agent-session",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )
    assert result.returncode != 0
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
    assert data.get("score") in (None, 0, 0.0)


def test_tool_packages_deterministic_pass() -> None:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    for package, task in (
        ("sdk-tool-guard", "sdk-tool-guard"),
        ("sdk-tool-guard-denied", "sdk-tool-guard-denied"),
    ):
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
        assert result.returncode == 0, (package, result.stdout, result.stderr)
        data = json.loads(result.stdout)
        assert data["status"] == "PASS"
