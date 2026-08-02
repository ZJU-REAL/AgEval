"""Public bora run acceptance (v0.6)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _bora(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Keep automated suite bounded; real Codex is optional operator path.
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


def test_agent_eval_offline_fail_closed() -> None:
    """With BORA_OFFLINE_AGENT=1, do not fabricate PASS for Codex packages."""
    result = _bora("run", str(REPO / "examples" / "agent-eval"), "--task", "agent-eval")
    # Fail-closed: harness missing agent result or evaluation ERROR — never silent PASS.
    assert result.returncode != 0, result.stdout
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert data["status"] in {"ERROR", "FAIL"}
        assert data.get("harness_kind") in {"failed", "completed", "unknown"}


def test_unknown_task() -> None:
    result = _bora("run", str(REPO / "examples" / "agent-eval"), "--task", "unknown")
    assert result.returncode == 2
    assert "unknown_task" in result.stderr
    assert result.stdout.strip() == ""


def test_evaluator_negative() -> None:
    result = _bora(
        "run",
        str(REPO / "examples" / "evaluator-negative"),
        "--task",
        "evaluator-negative",
    )
    assert result.returncode == 1, result.stderr + result.stdout
    data = json.loads(result.stdout)
    assert data["status"] == "FAIL"
    assert data["harness_kind"] == "completed"  # completed ≠ PASS
