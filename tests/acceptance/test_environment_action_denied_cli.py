"""Public CLI: undeclared Environment action denied before mutation (Spec 15)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "examples" / "core" / "environment-action-denied"


@pytest.mark.skipif(
    subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="docker required for postgres env",
)
def test_environment_action_denied_public_cli() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(PKG),
            "--task",
            "environment-action-denied",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["status"] == "PASS"
    logs = Path(data.get("logs") or data["evidence_path"])
    if not logs.is_absolute():
        logs = PKG / logs
    effects = logs / "effects.jsonl"
    assert effects.is_file()
    text = effects.read_text(encoding="utf-8")
    assert "deny" in text or "decision" in text
    # At least one deny decision recorded
    assert any(
        '"decision":"deny"' in line or '"decision": "deny"' in line
        for line in text.splitlines()
        if line.strip()
    )
