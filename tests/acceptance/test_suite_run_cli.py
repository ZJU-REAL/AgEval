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
    """Full suite without --task; concurrency flag accepted; FAIL continues."""
    r = _bora("run", str(SUITE), "--max-concurrent-tasks", "2")
    assert r.stdout.strip().startswith("{"), (r.stdout, r.stderr)
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data.get("schema") == "bora.suite.summary/1"
    assert data.get("database_id") == "test/suite-min"
    assert "tasks" in data and len(data["tasks"]) >= 3
    assert data.get("counts", {}).get("pass", 0) >= 3
    assert data.get("counts", {}).get("fail", 0) >= 1
    assert data.get("exit_code") == 1
    assert r.returncode == 1
    assert int(data.get("inflight_peak") or 0) <= 2
    assert data.get("note")
    assert "no suite-level" in data["note"]
    assert Path(data["summary_path"]).is_file()
    assert "suite_pass" not in data
    # Suite summary stores run_id only (no result_ref / evidence_ref).
    for row in data["tasks"]:
        assert "result_ref" not in row
        assert "evidence_ref" not in row
    run_ids = [t.get("run_id") for t in data["tasks"] if t.get("run_id")]
    assert len(run_ids) >= 3


def test_single_task_still_works() -> None:
    r = _bora("run", str(SUITE), "--task", "alpha", "--max-concurrent-tasks", "2")
    assert r.returncode == 0, (r.stdout, r.stderr)
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data.get("status") == "PASS"
    assert data.get("schema") != "bora.suite.summary/1"


def test_unknown_task_suite_cli() -> None:
    r = _bora("run", str(SUITE), "--task", "missing-task")
    assert r.returncode == 2
    assert "unknown_task" in r.stderr
