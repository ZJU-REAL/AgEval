"""Spec 06 named path: real AgentSession multi-invoke public smoke (optional network).

Default CI stays offline-safe: asserts fail-closed without silent PASS.
Real Codex PASS is recorded under package .ageval/runs and scratch case-runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_sdk_agent_session_offline_not_pass() -> None:
    env = os.environ.copy()
    env["AGEVAL_OFFLINE_AGENT"] = "1"
    env.pop("AGEVAL_SDK_SESSION_STUB", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
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
    assert "assurance" not in data


@pytest.mark.skipif(
    os.environ.get("AGEVAL_RUN_REAL_AGENT") != "1",
    reason="set AGEVAL_RUN_REAL_AGENT=1 for live Codex multi-invoke",
)
def test_sdk_agent_session_real_multi_invoke_pass() -> None:
    env = os.environ.copy()
    env.pop("AGEVAL_OFFLINE_AGENT", None)
    env.pop("AGEVAL_SDK_SESSION_STUB", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
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
        timeout=360,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["agent_invocations"] == 2
    assert "assurance" not in data
