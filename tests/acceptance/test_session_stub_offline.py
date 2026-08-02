"""Public path must not PASS when offline even if stub env is set."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_offline_plus_stub_not_pass() -> None:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    env["BORA_SDK_SESSION_STUB"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "sdk-agent-session"),
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
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] != "PASS"
    assert data.get("score") in (None, 0, 0.0)
