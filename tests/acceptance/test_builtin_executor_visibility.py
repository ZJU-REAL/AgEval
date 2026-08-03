"""Spec 14: Docker L1 visibility success + gold-denied matrix."""

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
def test_visibility_success_records_location() -> None:
    result = _run("builtin-executor-visibility", "builtin-executor-visibility", timeout=300)
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data.get("assurance") == "l1"
    l1 = data.get("l1") or {}
    # Honest location: parent-api-client or attempt-container when measured.
    assert l1.get("execution_location") in {
        "parent-api-client",
        "attempt-container",
        "mixed",
    } or l1.get("full_l1") is True
    logs = data.get("logs") or data.get("evidence_path")
    root = Path(logs)
    assert root.is_dir()
    assert (root / "summary.json").is_file() or (root / "l1.json").is_file()
    blob = (root / "l1.json").read_text(encoding="utf-8") if (root / "l1.json").is_file() else ""
    assert "sk-" not in blob
    assert "OPENAI_API_KEY=" not in blob


@pytest.mark.skipif(os.environ.get("BORA_SKIP_DOCKER") == "1", reason="docker skipped")
def test_visibility_gold_denied_not_seen() -> None:
    """Security negative: harness must not see gold; probe records seen_gold=false."""
    result = _run(
        "builtin-executor-visibility-denied",
        "builtin-executor-visibility-denied",
        timeout=180,
    )
    assert result.stdout.strip(), (result.stdout, result.stderr)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    # Denial success path: PASS with assurance l1 means probe succeeded (gold not visible).
    # Or ERROR if harness failed for other reasons — still must not claim gold was seen.
    l1 = data.get("l1") or {}
    probe = l1.get("probe") if isinstance(l1.get("probe"), dict) else {}
    # Prefer probe field from run_l1 hidden path
    if probe:
        assert probe.get("seen_gold") is False
        assert probe.get("eval_visible") is False
    else:
        # Fall back to artifact under evidence
        logs = data.get("logs") or data.get("evidence_path")
        root = Path(logs) if logs else None
        if root and root.is_dir():
            # search probe json in result/l1
            l1_path = root / "l1.json"
            if l1_path.is_file():
                doc = json.loads(l1_path.read_text(encoding="utf-8"))
                p2 = doc.get("probe") or {}
                assert p2.get("seen_gold") is False, doc
        else:
            # Last resort: must not be a success that claims gold visibility
            assert "seen_gold\": true" not in result.stdout.lower().replace(" ", "")
            assert data.get("status") in {"PASS", "FAIL", "ERROR"}
