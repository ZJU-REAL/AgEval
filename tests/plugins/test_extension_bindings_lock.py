"""Spec 00: bora lock writes per-profile extension_bindings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_lock_cli_extension_bindings_solver_acp() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "lock",
            str(ROOT / "examples/journeys"),
            "--task",
            "terminal-jsonl-agg",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    bindings = data["extension_bindings"]
    assert "solver" in bindings
    assert bindings["solver"]["executor"]["plugin"] == "acp"
    assert bindings["solver"]["executor"]["source"] == "profile_executor_field"
    assert bindings["solver"]["executor"]["kind"] == "provide"
    assert bindings["solver"]["before_agent_invoke"]["kind"] == "on"
    assert any(e.get("pointer") == "/extension_bindings" for e in data.get("resolution") or [])
