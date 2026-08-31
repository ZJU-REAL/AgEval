"""Public CLI: unknown/offline executor bindings fail closed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "examples" / "datasets" / "minimal-demo"
TASK = "terminal-jsonl-agg"


def test_unknown_executor_fail_closed(tmp_path: Path) -> None:
    dataset = Path(
        shutil.copytree(
            PACKAGE, tmp_path / "minimal-demo", ignore=shutil.ignore_patterns(".ageval", ".env")
        )
    )
    env = {**os.environ, "AGEVAL_OFFLINE_AGENT": "1"}
    env.setdefault("ZHIPU_API_KEY", "ci-offline-placeholder")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "run",
            str(dataset),
            "--task",
            TASK,
            "--set",
            '/agent_profiles/solver/options/entry="codex"',
            "--set",
            '/agent_profiles/solver/model="gpt-5.4-mini"',
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=180,
    )
    assert result.returncode != 0, result.stdout
    data = json.loads(result.stdout)
    assert data.get("status") != "PASS"
