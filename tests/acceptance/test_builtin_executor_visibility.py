"""Spec 14: positive L1 location via public package (isolation unit tests elsewhere)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _run(package: str, task: str, timeout: float = 360) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "l1" / package),
            "--task",
            task,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=timeout,
    )


@pytest.mark.skipif(os.environ.get("BORA_SKIP_DOCKER") == "1", reason="docker skipped")
@pytest.mark.skipif(os.environ.get("BORA_OFFLINE_AGENT") == "1", reason="offline agent")
def test_sdk_session_records_attempt_container_location() -> None:
    """Positive L1 path records attempt-container."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI missing")
    result = _run("sdk-session-single-actor", "sdk-session-single-actor")
    err = (result.stderr or "") + (result.stdout or "")
    if result.returncode != 0 and (
        "Docker daemon" in err or "Cannot connect to the Docker" in err
    ):
        pytest.skip("docker daemon unavailable")
    assert result.returncode == 0, err
    data = json.loads(result.stdout)
    assert data.get("status") == "PASS"
    l1 = data.get("l1") or {}
    loc = l1.get("execution_location") or l1.get("executor_containment")
    assert loc in {"attempt-container", "mixed"}
    assert int(l1.get("host_fallback_count") or 0) == 0
    logs = data.get("logs") or data.get("evidence_path")
    root = Path(str(logs))
    if (root / "l1.json").is_file():
        blob = (root / "l1.json").read_text(encoding="utf-8")
        assert "sk-" not in blob
        assert "OPENAI_API_KEY=" not in blob
