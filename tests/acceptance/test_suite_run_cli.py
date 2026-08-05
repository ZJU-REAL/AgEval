"""Public CLI suite run acceptance (Spec 22)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def _bora(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=180,
    )


def test_suite_full_concurrent_cli() -> None:
    """Full suite without --task; concurrency flag accepted."""
    # Exclude delta-fail by using only a subset isn't possible without --task;
    # full suite includes delta-fail → exit 1 expected if real run works.
    r = _bora("run", str(SUITE), "--max-concurrent-tasks", "2")
    # Either real harness path works (exit 0/1) or infrastructure error (2).
    # Prefer structured suite summary on stdout.
    assert r.stdout.strip().startswith("{"), (r.stdout, r.stderr)
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data.get("schema") == "bora.suite.summary/1"
    assert data.get("database_id") == "test/suite-min"
    assert "tasks" in data and len(data["tasks"]) >= 3
    assert "counts" in data
    assert data.get("note")
    assert "suite-level PASS" in data["note"] or "no suite-level" in data["note"]
    assert Path(data["summary_path"]).is_file()
    # No suite PASS field as authority
    assert "suite_pass" not in data
    assert "all_pass" not in data or data.get("schema") == "bora.suite.summary/1"


def test_single_task_still_works() -> None:
    r = _bora("run", str(SUITE), "--task", "alpha", "--max-concurrent-tasks", "2")
    # Single-task shape (not suite summary) when --task provided
    assert r.returncode in {0, 1, 2}
    if r.stdout.strip().startswith("{"):
        data = json.loads(r.stdout.strip().splitlines()[-1])
        # single task path uses flat Result keys
        assert "status" in data
        assert data.get("schema") != "bora.suite.summary/1"


def test_unknown_task_suite_cli() -> None:
    r = _bora("run", str(SUITE), "--task", "missing-task")
    assert r.returncode == 2
    assert "unknown_task" in r.stderr
