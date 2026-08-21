"""Public CLI: hard-ceiling N+1 invoke denial (Spec 16)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "examples" / "core"


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex required for first real invoke")
def test_n_plus_one_invoke_denied_public_cli() -> None:
    """Second invoke hits agent_invocation_limit; evaluator PASS on denial probe."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "run",
            str(PKG),
            "--task",
            "hard-ceiling-min",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=300,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["status"] == "PASS"
    # Refused before the external effect, so nothing was counted as spent.
    assert data.get("agent_invocations") == 0
    logs = Path(data.get("logs") or data["evidence_path"])
    if not logs.is_absolute():
        logs = PKG / logs
    assert logs.is_dir()
