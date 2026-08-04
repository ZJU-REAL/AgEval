"""L1 packages require environment/Dockerfile; lock fails without it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OFFICIAL = REPO / "examples" / "l1" / "executor-image-official"
UPSTREAM = REPO / "examples" / "l1" / "executor-image-upstream"


def _run_bora(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=os.environ.copy(),
    )


def test_official_package_has_environment_dockerfile() -> None:
    assert (OFFICIAL / "environment" / "Dockerfile").is_file()
    text = (OFFICIAL / "environment" / "Dockerfile").read_text(encoding="utf-8")
    assert "bora-attempt:l1" in text


def test_upstream_package_from_python_slim() -> None:
    assert (UPSTREAM / "environment" / "Dockerfile").is_file()
    text = (UPSTREAM / "environment" / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12-slim" in text
    assert (UPSTREAM / "environment" / "install-executors.sh").is_file()


def test_lock_official_package() -> None:
    r = _run_bora("lock", str(OFFICIAL), "--task", "executor-image-official")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["task_id"] == "executor-image-official"


def test_lock_upstream_package() -> None:
    r = _run_bora("lock", str(UPSTREAM), "--task", "executor-image-upstream")
    assert r.returncode == 0, r.stderr
