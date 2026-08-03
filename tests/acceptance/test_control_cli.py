"""Spec 12: durable ControlStore CLI surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_submit_status_cancel(tmp_path: Path) -> None:
    store = tmp_path / "control.db"
    # Use tool-guard (no agent) for fast durable path.
    # Wait mode for deterministic unit path.
    submit = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "submit",
            str(REPO / "examples" / "core" / "sdk-tool-guard"),
            "--task",
            "sdk-tool-guard",
            "--store",
            str(store),
            "--wait",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=120,
    )
    assert submit.returncode == 0, (submit.stdout, submit.stderr)
    data = json.loads(submit.stdout)
    run_id = data["run_id"]
    st = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "status", run_id, "--store", str(store)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=30,
    )
    assert st.returncode == 0
    rec = json.loads(st.stdout)
    assert rec["ok"] is True
    assert rec["status"] in {"completed", "failed", "running"}
    cancel = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "cancel", run_id, "--store", str(store)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=30,
    )
    assert cancel.returncode == 0
    assert json.loads(cancel.stdout)["status"] == "cancelled"
