"""Phase 0: real Docker feasibility probes for L1."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def test_build_image_lock(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(REPO / "docker" / "attempt" / "build.py"),
            "--platform",
            "linux/arm64",
            "--output-lock",
            str(lock),
            "--tag",
            "ageval-attempt:l1-test",
        ],
        check=False,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["platform"] == "linux/arm64"
    assert data["image_digest"]
    assert data["build_input_digest"].startswith("sha256:")


def test_container_no_docker_socket() -> None:
    # Ensure image exists
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(REPO / "docker" / "attempt" / "build.py"),
            "--tag",
            "ageval-attempt:l1-test",
            "--output-lock",
            str(REPO / ".ageval" / "runtime-images" / "provider-l1-test.json"),
        ],
        check=False,
        cwd=str(REPO),
        capture_output=True,
    )
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "ageval-attempt:l1-test",
            "python",
            "-c",
            "import os; print(os.path.exists('/var/run/docker.sock'))",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "False"


def test_network_none_denies_egress() -> None:
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "ageval-attempt:l1-test",
            "python",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 53), 2)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0
