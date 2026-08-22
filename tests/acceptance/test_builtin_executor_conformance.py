"""Public CLI: unknown/offline executor bindings fail closed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "examples" / "core"


def test_unknown_executor_fail_closed() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "run",
            str(PACKAGE),
            "--task",
            "builtin-executor-conformance",
            "--set",
            '/agent_profiles/solver/options/entry="codex"',
            "--set",
            '/agent_profiles/solver/model="gpt-5.4-mini"',
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env={**os.environ, "AGEVAL_OFFLINE_AGENT": "1"},
        timeout=120,
    )
    assert result.returncode != 0
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")]
    if lines:
        assert json.loads(lines[-1]).get("status") != "PASS"
