"""Public ageval run acceptance (v0.6)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _ageval(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Keep automated suite bounded; real Codex is optional operator path.
    env["AGEVAL_OFFLINE_AGENT"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "ageval.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )


def test_agent_package_offline_fail_closed() -> None:
    """With AGEVAL_OFFLINE_AGENT=1, do not fabricate PASS for agent packages."""
    result = _ageval("run", str(REPO / "examples" / "core"), "--task", "sdk-agent-session")
    # Fail-closed: harness missing agent result or evaluation ERROR — never silent PASS.
    assert result.returncode != 0, result.stdout
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert data["status"] in {"ERROR", "FAIL"}
        assert data.get("score") in (None, 0, 0.0)
        assert data.get("harness_kind") in {"failed", "completed", "unknown"}


def test_offline_plus_session_stub_not_pass() -> None:
    """Stub env must not manufacture PASS under offline (session authority)."""
    env = os.environ.copy()
    env["AGEVAL_OFFLINE_AGENT"] = "1"
    env["AGEVAL_SDK_SESSION_STUB"] = "1"
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
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
    assert data.get("score") in (None, 0, 0.0)


def test_stale_agent_result_cannot_force_pass(tmp_path: Path) -> None:
    """Pre-placed .ageval_agent_result.json must not produce offline PASS (Codex B-01)."""
    import shutil

    db = tmp_path / "db"
    db.mkdir()
    (db / "ageval.yaml").write_text(
        "format: ageval.dataset/1\n"
        "dataset_id: test/stale-agent\n"
        'version: "0.0.1"\n'
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    task_dir = db / "tasks" / "sdk-agent-session"
    shutil.copytree(REPO / "examples" / "core" / "tasks" / "sdk-agent-session", task_dir)
    # Job bindings live at Dataset root (#59).
    shutil.copy(
        REPO / "examples" / "core" / "profiles.yaml",
        db / "profiles.yaml",
    )
    stale = task_dir / ".ageval_agent_result.json"
    stale.write_text(json.dumps({"answer": 42, "source": "stale"}) + "\n", encoding="utf-8")
    result = _ageval("run", str(db), "--task", "sdk-agent-session")
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
    assert data["status"] in {"ERROR", "FAIL"}
    # Stale file must be cleared before attempt; must not survive as success material.
    assert not stale.is_file() or data["status"] != "PASS"


def test_unknown_task() -> None:
    result = _ageval("run", str(REPO / "examples" / "core"), "--task", "unknown")
    assert result.returncode == 2
    assert "unknown_task" in result.stderr
    assert result.stdout.strip() == ""


def test_evaluator_negative() -> None:
    result = _ageval(
        "run",
        str(REPO / "examples" / "core"),
        "--task",
        "evaluator-negative",
    )
    assert result.returncode == 1, result.stderr + result.stdout
    data = json.loads(result.stdout)
    assert data["status"] == "FAIL"
    assert data["harness_kind"] == "completed"  # completed ≠ PASS
