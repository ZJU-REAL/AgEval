"""L1 packages require environment/Dockerfile; lock fails without it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def _assert_trajectory_layout(logs: Path) -> None:
    inv = logs / "agent" / "invocations"
    assert inv.is_dir(), f"missing {inv}"
    dirs = [p for p in inv.iterdir() if p.is_dir()]
    assert dirs, "no invocation directories"
    for d in dirs:
        assert (d / "backend_raw" / "backend-stdout.jsonl").is_file()
        assert (d / "metadata.json").is_file()
        assert (d / "request.json").is_file()
        assert (d / "events.jsonl").is_file()
        # Must not be empty for a successful pi invoke.
        assert (d / "backend_raw" / "backend-stdout.jsonl").stat().st_size > 0


@pytest.mark.skipif(
    os.environ.get("BORA_SKIP_L1_DOCKER") == "1",
    reason="BORA_SKIP_L1_DOCKER=1",
)
def test_run_official_persists_trajectory_and_container() -> None:
    r = _run_bora("run", str(OFFICIAL), "--task", "executor-image-official")
    if r.returncode != 0 and "Docker daemon" in (r.stderr or r.stdout or ""):
        pytest.skip("docker unavailable")
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    assert data.get("status") == "PASS"
    assert data.get("l1", {}).get("executor_containment") == "container"
    logs = Path(data["logs"])
    _assert_trajectory_layout(logs)
    # agent.json must not embed multi-MB stream blob
    agent = json.loads((logs / "agent.json").read_text(encoding="utf-8"))
    assert "container_stdout" not in agent


def test_run_upstream_persists_trajectory_and_container() -> None:
    r = _run_bora("run", str(UPSTREAM), "--task", "executor-image-upstream")
    if r.returncode != 0 and "Docker daemon" in (r.stderr or r.stdout or ""):
        pytest.skip("docker unavailable")
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    assert data.get("status") == "PASS"
    assert data.get("l1", {}).get("executor_containment") == "container"
    _assert_trajectory_layout(Path(data["logs"]))
