"""Public CLI: sdk-agent-session stays fail-closed without a live Agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_sdk_agent_session_offline_not_pass() -> None:
    env = os.environ.copy()
    env["AGEVAL_OFFLINE_AGENT"] = "1"
    env.pop("AGEVAL_SDK_SESSION_STUB", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "run",
            str(REPO / "examples" / "core"),
            "--task",
            "sdk-agent-session",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )
    assert result.returncode != 0
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")]
    if lines:
        data = json.loads(lines[-1])
        assert data.get("status") != "PASS"
        assert "assurance" not in data
