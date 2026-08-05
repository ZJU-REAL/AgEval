"""Spec 14: Docker L1 gold-denied + positive location (lean)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _run(package: str, task: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
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
def test_visibility_gold_denied_not_seen() -> None:
    """Security negative: harness must not see gold (provider-l1-denied probe)."""
    result = _run("provider-l1-denied", "hidden-material-denied", timeout=180)
    assert result.stdout.strip(), (result.stdout, result.stderr)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    l1 = data.get("l1") if isinstance(data.get("l1"), dict) else {}
    probe = l1.get("probe") if isinstance(l1.get("probe"), dict) else {}
    if not probe:
        logs = data.get("logs") or data.get("evidence_path")
        root = Path(str(logs)) if logs else None
        if root and (root / "l1.json").is_file():
            doc = json.loads((root / "l1.json").read_text(encoding="utf-8"))
            probe = doc.get("probe") if isinstance(doc.get("probe"), dict) else {}
    assert isinstance(probe, dict) and probe, f"missing l1.probe: {data}"
    assert probe.get("seen_gold") is False
    assert probe.get("eval_visible") is False


@pytest.mark.skipif(os.environ.get("BORA_SKIP_DOCKER") == "1", reason="docker skipped")
@pytest.mark.skipif(os.environ.get("BORA_OFFLINE_AGENT") == "1", reason="offline agent")
def test_sdk_session_records_attempt_container_location() -> None:
    """Positive L1 path records attempt-container (replaces deleted visibility package)."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI missing")
    result = _run("sdk-session-single-actor", "sdk-session-single-actor", timeout=360)
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
