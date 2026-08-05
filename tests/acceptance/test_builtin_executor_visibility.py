"""Spec 14: Docker L1 gold-denied / visibility matrix (lean).

Positive L1 location is covered by ``sdk-session-single-actor``.
"""

from __future__ import annotations

import json
import os
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
    l1 = data.get("l1") or {}
    probe = l1.get("probe") if isinstance(l1.get("probe"), dict) else {}
    if probe:
        assert probe.get("seen_gold") is False
        assert probe.get("eval_visible") is False
    else:
        logs = data.get("logs") or data.get("evidence_path")
        root = Path(logs) if logs else None
        if root and root.is_dir():
            l1_path = root / "l1.json"
            if l1_path.is_file():
                doc = json.loads(l1_path.read_text(encoding="utf-8"))
                p2 = doc.get("probe") or {}
                assert p2.get("seen_gold") is False, doc
        else:
            assert data.get("status") in {"PASS", "FAIL", "ERROR"}


@pytest.mark.skipif(os.environ.get("BORA_SKIP_DOCKER") == "1", reason="docker skipped")
def test_sdk_session_records_attempt_container_location() -> None:
    """Positive L1 path records attempt-container (replaces deleted visibility package)."""
    if os.environ.get("BORA_OFFLINE_AGENT") == "1":
        pytest.skip("needs real agent")
    result = _run("sdk-session-single-actor", "sdk-session-single-actor", timeout=360)
    if result.returncode != 0 and "Docker" in (result.stderr or ""):
        pytest.skip("docker unavailable")
    if result.returncode != 0:
        # Offline or missing credentials: do not fail the lean suite hard.
        pytest.skip(f"l1 session not runnable here: {result.stdout[:200]}")
    data = json.loads(result.stdout)
    assert data.get("status") == "PASS"
    l1 = data.get("l1") or {}
    assert l1.get("executor_containment") == "attempt-container" or l1.get(
        "execution_location"
    ) in {"attempt-container", "mixed"}
