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


def test_agent_package_offline_fail_closed() -> None:
    """With BORA_OFFLINE_AGENT=1, do not fabricate PASS for Codex packages."""
    result = _bora("run", str(REPO / "examples" / "core" / "sdk-agent-session"), "--task", "sdk-agent-session")
    # Fail-closed: harness missing agent result or evaluation ERROR — never silent PASS.
    assert result.returncode != 0, result.stdout
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert data["status"] in {"ERROR", "FAIL"}
        assert data.get("harness_kind") in {"failed", "completed", "unknown"}


def test_stale_agent_result_cannot_force_pass(tmp_path: Path) -> None:
    """Pre-placed .bora_agent_result.json must not produce offline PASS (Codex B-01)."""
    import shutil

    pkg = tmp_path / "sdk-agent-session"
    shutil.copytree(REPO / "examples" / "core" / "sdk-agent-session", pkg)
    stale = pkg / ".bora_agent_result.json"
    stale.write_text(json.dumps({"answer": 42, "source": "stale"}) + "\n", encoding="utf-8")
    result = _bora("run", str(pkg), "--task", "sdk-agent-session")
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
    assert data["status"] in {"ERROR", "FAIL"}
    # Stale file must be cleared before attempt; must not survive as success material.
    assert not stale.is_file() or data["status"] != "PASS"


def test_sdk_agent_session_offline_no_stub_pass() -> None:
    """AgentSession must not manufacture answer:42 offline (Codex B-01)."""
    result = _bora(
        "run",
        str(REPO / "examples" / "core" / "sdk-agent-session"),
        "--task",
        "sdk-agent-session",
    )
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"


def test_unknown_task() -> None:
    result = _bora("run", str(REPO / "examples" / "core" / "sdk-agent-session"), "--task", "unknown")
    assert result.returncode == 2
    assert "unknown_task" in result.stderr
    assert result.stdout.strip() == ""


def test_evaluator_negative() -> None:
    result = _bora(
        "run",
        str(REPO / "examples" / "core" / "evaluator-negative"),
        "--task",
        "evaluator-negative",
    )
    assert result.returncode == 1, result.stderr + result.stdout
    data = json.loads(result.stdout)
    assert data["status"] == "FAIL"
    assert data["harness_kind"] == "completed"  # completed ≠ PASS
